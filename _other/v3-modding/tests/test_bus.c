#include "bus_packet.h"
#include "softwire.h"
#include "node.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static bus_packet_t request_for(uint8_t operation)
{
    return (bus_packet_t){.destination=7,.source=0,.operation=operation,.transaction=0x12345678};
}
static void packet_integrity(void)
{
    assert(bus_crc16((const uint8_t *)"123456789",9)==0x29b1);
    bus_packet_t q=request_for(BUS_OP_PING),r;
    for (unsigned i=0;i<12;++i) q.payload[i]=(uint8_t)(i*19u);
    uint8_t frame[BUS_FRAME_SIZE]; bus_encode(&q,frame);
    assert(bus_decode(frame,&r)); assert(r.transaction==q.transaction);
    assert(memcmp(q.payload,r.payload,12)==0);
    for (unsigned i=0;i<BUS_FRAME_SIZE;++i) for (unsigned bit=0;bit<8;++bit) {
        frame[i]^=(uint8_t)(1u<<bit);assert(!bus_decode(frame,&r));frame[i]^=(uint8_t)(1u<<bit);
    }
    r=q;r.source=7;r.destination=0;r.operation|=BUS_REPLY;
    assert(bus_matches_reply(&q,&r));++r.transaction;assert(!bus_matches_reply(&q,&r));
    r.transaction=q.transaction;r.source=8;assert(!bus_matches_reply(&q,&r));
    q.destination=0;assert(!bus_is_request(&q));q.destination=248;assert(!bus_is_request(&q));
}
static void fixed_wire_vector(void)
{
    bus_packet_t p=request_for(BUS_OP_PING);memcpy(p.payload,"wire test",9);
    uint8_t frame[BUS_FRAME_SIZE];bus_encode(&p,frame);
    /* CRC independently calculated by Python binascii.crc_hqx in client tests. */
    const uint8_t golden[BUS_FRAME_SIZE]={0xa5,0x5a,1,7,0,1,0x78,0x56,0x34,0x12,
        'w','i','r','e',' ','t','e','s','t',0,0,0,0x98,0xc4};
    assert(memcmp(frame,golden,sizeof(frame))==0);
}
static void parser_recovers(void)
{
    bus_packet_t q=request_for(BUS_OP_STATUS),r;uint8_t frame[BUS_FRAME_SIZE];bus_encode(&q,frame);
    bus_parser_t p;bus_parser_init(&p);
    const uint8_t noise[]={0,0xa5,0xa5,0x5a,1,3,9};
    for (unsigned i=0;i<sizeof(noise);++i) assert(!bus_parser_byte(&p,noise[i],0,&r));
    unsigned found=0;
    for (unsigned i=0;i<sizeof(frame);++i) if (bus_parser_byte(&p,frame[i],1,&r)) ++found;
    assert(found==1 && r.transaction==q.transaction);
    bus_parser_init(&p);
    for (unsigned i=0;i<10;++i) assert(!bus_parser_byte(&p,frame[i],UINT32_MAX-3,&r));
    /* A gap over 10 ms resets a partial frame, including across clock rollover. */
    found=0;
    for (unsigned i=0;i<sizeof(frame);++i) if (bus_parser_byte(&p,frame[i],20,&r)) ++found;
    assert(found==1);
    frame[7]^=1;found=0;
    for (unsigned i=0;i<sizeof(frame);++i) if (bus_parser_byte(&p,frame[i],21,&r)) ++found;
    assert(found==0);
    frame[7]^=1;
    for (unsigned i=0;i<sizeof(frame);++i) if (bus_parser_byte(&p,frame[i],22,&r)) ++found;
    assert(found==1);
}
static void tick_pair(softwire_t *a,softwire_t *b,unsigned ticks)
{
    for (unsigned i=0;i<ticks;++i) {
        const bool high=!(a->drive_low || b->drive_low);
        (void)softwire_tick(a,high);(void)softwire_tick(b,high);
    }
}
static void physical_layer_roundtrip(void)
{
    softwire_t a,b;softwire_init(&a);softwire_init(&b);
    assert(!softwire_send(&a,(const uint8_t *)"",0));
    uint8_t data[32];
    for (unsigned block=0;block<8;++block) {
        for (unsigned i=0;i<32;++i) data[i]=(uint8_t)(block*32u+i);
        assert(softwire_send(&a,data,sizeof(data)));assert(!softwire_send(&a,data,1));
        tick_pair(&a,&b,32*40+30);
        assert(!softwire_busy(&a));
        for (unsigned i=0;i<32;++i) { uint8_t value;assert(softwire_read(&b,&value));assert(value==data[i]); }
        uint8_t empty;assert(!softwire_read(&a,&empty));assert(!softwire_read(&b,&empty));
    }
    assert(a.collisions==0 && b.framing_errors==0 && b.overruns==0);
    assert(softwire_send(&b,data,24));tick_pair(&a,&b,1000);
    for (unsigned i=0;i<24;++i) { uint8_t value;assert(softwire_read(&a,&value));assert(value==data[i]); }
}
static void electrical_faults_are_observable(void)
{
    softwire_t a,b;softwire_init(&a);softwire_init(&b);
    const uint8_t one=0xff,zero=0;
    assert(softwire_send(&a,&one,1));assert(softwire_send(&b,&zero,1));
    tick_pair(&a,&b,60);assert(a.collisions>0);assert(!a.drive_low);
    softwire_init(&a);
    for (unsigned i=0;i<80;++i) assert(!softwire_tick(&a,false));
    assert(a.framing_errors>0);assert(!a.drive_low);
    softwire_init(&a);softwire_init(&b);
    uint8_t lots[64];memset(lots,0x55,sizeof(lots));
    assert(softwire_send(&a,lots,64));tick_pair(&a,&b,2600);
    assert(b.overruns==1); /* 63 usable ring-buffer entries. */
    softwire_timing_fault(&a);assert(a.timing_errors==1 && !softwire_busy(&a) && !a.drive_low);
}
static void bench_node_never_starts_motion(void)
{
    uint8_t uid[12];for (unsigned i=0;i<12;++i) uid[i]=(uint8_t)(i+1);
    feeder_node_t n;assert(!feeder_node_init(&n,0,uid));assert(feeder_node_init(&n,7,uid));
    bus_packet_t q=request_for(BUS_OP_FEED),r;
    for (unsigned i=0;i<3;++i) {
        assert(feeder_node_request(&n,&q,100,0,&r));
        assert(r.payload[0]==BUS_RESULT_INHIBITED);assert(!feed_cycle_motor_requested(&n.cycle));
    }
    q.operation=BUS_OP_UID;assert(feeder_node_request(&n,&q,100,0,&r));assert(memcmp(r.payload,uid,12)==0);
    q.operation=BUS_OP_INPUTS;assert(feeder_node_request(&n,&q,100,5,&r));assert(r.payload[1]==5);
    q.operation=BUS_OP_STATUS;assert(feeder_node_request(&n,&q,1234,0,&r));
    assert(r.payload[1]==FEED_IDLE && r.payload[3]==0 && bus_get_u32(r.payload+8)==1234);
    q.operation=0x7e;assert(feeder_node_request(&n,&q,0,0,&r));assert(r.payload[0]==BUS_RESULT_UNSUPPORTED);
    q.destination=255;assert(!feeder_node_request(&n,&q,0,0,&r));
    q.destination=7;q.source=2;assert(!feeder_node_request(&n,&q,0,0,&r));
}
static void end_to_end_wire_exchange(void)
{
    softwire_t host,device;softwire_init(&host);softwire_init(&device);
    feeder_node_t node;const uint8_t uid[12]={0};assert(feeder_node_init(&node,7,uid));
    bus_packet_t request=request_for(BUS_OP_PING),received,reply;memcpy(request.payload,"wire test",9);
    uint8_t bytes[BUS_FRAME_SIZE];bus_encode(&request,bytes);assert(softwire_send(&host,bytes,sizeof(bytes)));
    tick_pair(&host,&device,1000);
    bus_parser_t parser;bus_parser_init(&parser);bool complete=false;uint8_t value;
    while (softwire_read(&device,&value)) if (bus_parser_byte(&parser,value,26,&received)) complete=true;
    assert(complete && feeder_node_request(&node,&received,26,0,&reply));
    bus_encode(&reply,bytes);assert(softwire_send(&device,bytes,sizeof(bytes)));tick_pair(&host,&device,1000);
    bus_parser_init(&parser);complete=false;
    while (softwire_read(&host,&value)) if (bus_parser_byte(&parser,value,52,&received)) complete=true;
    assert(complete && bus_matches_reply(&request,&received));assert(memcmp(received.payload,request.payload,12)==0);
}
void bus_tests(void)
{
    packet_integrity();fixed_wire_vector();parser_recovers();physical_layer_roundtrip();electrical_faults_are_observable();
    bench_node_never_starts_motion();end_to_end_wire_exchange();
    puts("Bus tests passed (7 groups, all 256 UART byte values, CRC mutations and end-to-end simulated exchange)");
}
