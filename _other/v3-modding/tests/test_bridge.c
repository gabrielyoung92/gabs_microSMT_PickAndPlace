#include "controller.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    bridge_controller_t bridge;
    uint8_t sent[BUS_FRAME_SIZE];
    unsigned sends,cancels;
    bool reject;
    char output[8192];
} bridge_fixture_t;
static bool bridge_test_send(void *arg,const uint8_t frame[BUS_FRAME_SIZE])
{
    bridge_fixture_t *f=arg;
    if (f->reject) return false;
    memcpy(f->sent,frame,BUS_FRAME_SIZE);++f->sends;return true;
}
static void bridge_test_cancel(void *arg) {++((bridge_fixture_t *)arg)->cancels;}
static void bridge_test_emit(void *arg,const char *line)
{
    bridge_fixture_t *f=arg;
    assert(strlen(f->output)+strlen(line)+2<sizeof(f->output));
    strcat(f->output,line);strcat(f->output,"\n");
}
static void bridge_setup(bridge_fixture_t *f)
{
    memset(f,0,sizeof(*f));
    bridge_init(&f->bridge,(bridge_io_t){f,bridge_test_send,bridge_test_cancel,bridge_test_emit});
}
static void bridge_line(bridge_fixture_t *f,const char *line,uint32_t now)
{
    while (*line) bridge_input(&f->bridge,(uint8_t)*line++,now);
    bridge_input(&f->bridge,'\n',now);
}
static void bridge_reply(bridge_fixture_t *f,uint32_t now)
{
    bus_packet_t q,r;assert(bus_decode(f->sent,&q));
    const uint8_t uid[12]={1,2,3,4,5,6,7,8,9,10,11,12};
    feeder_node_t node;assert(feeder_node_init(&node,q.destination,uid));
    assert(feeder_node_request(&node,&q,now,5,&r));
    uint8_t frame[BUS_FRAME_SIZE];bus_encode(&r,frame);
    for (unsigned i=0;i<BUS_FRAME_SIZE;++i) bridge_receive(&f->bridge,frame[i],now);
}
static void bridge_diagnostics(void)
{
    bridge_fixture_t f;bridge_setup(&f);
    bridge_line(&f,"INFO",0);assert(strstr(f.output,"MOTION=INHIBITED"));assert(f.sends==0);
    const char *commands[]={"PING 7","STATUS 7","INPUTS 7","UID 7"};
    const char *expected[]={"PING address=7 OK","STATUS address=7 state=0 fault=0 motion_enabled=0 uptime_ms=50",
                           "INPUTS address=7 raw=5","UID address=7 uid=0102030405060708090A0B0C"};
    uint32_t previous=0;
    for (unsigned i=0;i<4;++i) {
        f.output[0]='\0';bridge_line(&f,commands[i],0);
        assert(f.bridge.active && f.bridge.pending.transaction!=previous);
        previous=f.bridge.pending.transaction;bridge_reply(&f,50);
        assert(!f.bridge.active && strstr(f.output,expected[i]));
    }
}
static void bridge_rejects_bad_commands(void)
{
    bridge_fixture_t f;bridge_setup(&f);
    const char *bad[]={"UID 0","UID 248","UID -1","UID +1","UID 99999999999999","UID 1 extra",
        "UID 1 ","SCAN 5 4","SCAN 1","SCAN 0 2","SCAN 1 248","SCAN 1 2 x","FEED 1","", "XFER invalid"};
    for (unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);++i) {
        f.output[0]='\0';bridge_line(&f,bad[i],0);
        assert(strcmp(f.output,"ERR REQUEST\n")==0 && !f.bridge.active && !f.bridge.scanning);
    }
    assert(f.sends==0);
    for (unsigned i=0;i<100;++i) bridge_input(&f.bridge,'A',0);
    bridge_line(&f,"",0);assert(strstr(f.output,"ERR LINE_TOO_LONG"));
    bridge_line(&f,"UID 1\r",0);assert(f.sends==1);
    bridge_disconnect(&f.bridge);
    bridge_input(&f.bridge,0,0);bridge_line(&f,"UID 1",0);assert(f.sends==1);
}
static void bridge_scans_bounded_range(void)
{
    bridge_fixture_t f;bridge_setup(&f);
    bridge_line(&f,"SCAN 1 3",0);bridge_poll(&f.bridge,0,(bridge_stats_t){0});
    assert(f.bridge.pending.destination==1 && f.bridge.pending.operation==BUS_OP_UID);
    bridge_reply(&f,50);bridge_poll(&f.bridge,50,(bridge_stats_t){0});
    assert(f.bridge.pending.destination==2);
    bridge_poll(&f.bridge,199,(bridge_stats_t){0});assert(f.sends==2);
    bridge_poll(&f.bridge,200,(bridge_stats_t){0});assert(f.bridge.pending.destination==3);
    bridge_reply(&f,250);bridge_poll(&f.bridge,250,(bridge_stats_t){0});
    assert(!f.bridge.scanning && !f.bridge.active && f.sends==3);
    assert(strstr(f.output,"MISS address=2 reason=TIMEOUT"));
    assert(strstr(f.output,"SCAN END found=2 missing=1 reason=COMPLETE"));
    bridge_line(&f,"SCAN 247 247",300);bridge_poll(&f.bridge,300,(bridge_stats_t){0});
    bridge_reply(&f,350);bridge_poll(&f.bridge,350,(bridge_stats_t){0});
    assert(!f.bridge.scanning && f.sends==4);
}
static void bridge_cancel_and_disconnect(void)
{
    bridge_fixture_t f;bridge_setup(&f);
    bridge_line(&f,"SCAN 1 247",0);bridge_poll(&f.bridge,0,(bridge_stats_t){0});
    bridge_line(&f,"UID 9",10);assert(strstr(f.output,"ERR BUSY") && f.sends==1);
    bridge_line(&f,"STATS",10);assert(strstr(f.output,"active=1 scan=1"));
    bridge_line(&f,"ABORT",10);assert(!f.bridge.active && !f.bridge.scanning);
    assert(strstr(f.output,"reason=ABORT") && strstr(f.output,"OK ABORT"));
    bridge_reply(&f,20);bridge_poll(&f.bridge,1000,(bridge_stats_t){0});assert(f.sends==1);
    bridge_line(&f,"SCAN 1 3",1000);bridge_poll(&f.bridge,1000,(bridge_stats_t){0});
    bridge_input(&f.bridge,'U',1000);bridge_disconnect(&f.bridge);
    assert(f.bridge.length==0 && !f.bridge.active && !f.bridge.scanning);
    bridge_poll(&f.bridge,5000,(bridge_stats_t){0});assert(f.sends==2);
    bridge_line(&f,"INFO",5000);assert(strstr(f.output,"MICROSMT BRIDGE"));
}
static void bridge_faults_and_rollover(void)
{
    bridge_fixture_t f;bridge_setup(&f);
    bridge_line(&f,"UID 1",UINT32_MAX-99u);
    bridge_poll(&f.bridge,49,(bridge_stats_t){0});assert(f.bridge.active);
    bridge_poll(&f.bridge,50,(bridge_stats_t){0});assert(!f.bridge.active && strstr(f.output,"ERR TIMEOUT"));
    bridge_line(&f,"SCAN 1 3",100);bridge_poll(&f.bridge,100,(bridge_stats_t){0});
    bridge_poll(&f.bridge,110,(bridge_stats_t){.collision=1});
    assert(!f.bridge.active && !f.bridge.scanning && strstr(f.output,"reason=LINK"));
    unsigned sends=f.sends;bridge_poll(&f.bridge,1000,(bridge_stats_t){.collision=1});assert(f.sends==sends);
    f.reject=true;bridge_line(&f,"PING 2",1000);assert(strstr(f.output,"ERR BUSY") && !f.bridge.active);
    bridge_line(&f,"SCAN 1 2",1000);bridge_poll(&f.bridge,1000,(bridge_stats_t){.collision=1});
    assert(!f.bridge.scanning && strstr(f.output,"reason=BUSY"));
}
static void bridge_ignores_wrong_or_late_reply(void)
{
    bridge_fixture_t f;bridge_setup(&f);bridge_line(&f,"UID 7",0);
    bus_packet_t q,r;assert(bus_decode(f.sent,&q));
    r=q;r.source=7;r.destination=0;r.operation|=BUS_REPLY;r.transaction++;
    uint8_t frame[BUS_FRAME_SIZE];bus_encode(&r,frame);
    for (unsigned i=0;i<BUS_FRAME_SIZE;++i) bridge_receive(&f.bridge,frame[i],20);
    assert(f.bridge.active && !f.output[0]);
    bridge_reply(&f,150);assert(f.bridge.active && !f.output[0]);
    bridge_poll(&f.bridge,150,(bridge_stats_t){0});assert(strstr(f.output,"ERR TIMEOUT"));
    bridge_line(&f,"UID 7",151);bridge_reply(&f,200);assert(!f.bridge.active);
}
static void bridge_raw_compatibility_and_motion_gate(void)
{
    bridge_fixture_t f;bridge_setup(&f);
    bus_packet_t q={.destination=7,.operation=BUS_OP_UID,.transaction=0x12345678};
    uint8_t frame[BUS_FRAME_SIZE];char cmd[64];
    for (unsigned pass=0;pass<2;++pass) {
        q.operation=pass==0 ? BUS_OP_UID : BUS_OP_FEED;
        bus_encode(&q,frame);memcpy(cmd,"XFER ",5);
        for (unsigned i=0;i<BUS_FRAME_SIZE;++i) (void)snprintf(cmd+5+2*i,3,"%02X",frame[i]);
        f.output[0]='\0';bridge_line(&f,cmd,0);
        if (pass==0) {bridge_reply(&f,50);assert(strncmp(f.output,"RX A55A",7)==0);}
        else assert(strcmp(f.output,"ERR REQUEST\n")==0 && f.sends==1);
    }
}
void bridge_tests(void)
{
    bridge_diagnostics();bridge_rejects_bad_commands();bridge_scans_bounded_range();
    bridge_cancel_and_disconnect();bridge_faults_and_rollover();
    bridge_ignores_wrong_or_late_reply();bridge_raw_compatibility_and_motion_gate();
    puts("Bridge tests passed (7 groups: diagnostics, input validation, scan, cancellation, faults, correlation, motion gate)");
}
