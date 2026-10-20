#include "controller.h"
#include <stdio.h>
#include <string.h>

static void emit(bridge_controller_t *b, const char *text)
{
    b->io.emit(b->io.context, text);
}
static void stop(bridge_controller_t *b)
{
    b->io.cancel(b->io.context);
    b->active=false;
    bus_parser_init(&b->parser);
}
static void finish_scan(bridge_controller_t *b, const char *reason)
{
    char line[96];
    (void)snprintf(line,sizeof(line),"SCAN END found=%u missing=%u reason=%s",
                   (unsigned)b->found,(unsigned)b->missing,reason);
    b->scanning=false;
    emit(b,line);
}
void bridge_init(bridge_controller_t *b, bridge_io_t io)
{
    memset(b,0,sizeof(*b));
    b->io=io;
    b->next_transaction=1;
}
void bridge_disconnect(bridge_controller_t *b)
{
    stop(b);
    b->scanning=false;
    b->length=0;
    b->discard=false;
}
static bool begin(bridge_controller_t *b, bus_packet_t request, bool raw, uint32_t now)
{
    uint8_t frame[BUS_FRAME_SIZE];
    bus_encode(&request,frame);
    /* Flush previous RX and release any previous transmission before a new one. */
    stop(b);
    if (!b->io.send(b->io.context,frame)) return false;
    b->pending=request;
    b->baseline=b->stats;
    b->started=now;
    b->raw=raw;
    b->active=true;
    return true;
}
static bus_packet_t diagnostic(bridge_controller_t *b, uint8_t address, uint8_t operation)
{
    const bus_packet_t q={.destination=address,.operation=operation,
                          .transaction=b->next_transaction++};
    return q;
}
static bool changed(bridge_stats_t a, bridge_stats_t c)
{
    return a.framing!=c.framing || a.overrun!=c.overrun ||
           a.collision!=c.collision || a.timing!=c.timing;
}
void bridge_poll(bridge_controller_t *b, uint32_t now, bridge_stats_t stats)
{
    b->stats=stats;
    if (b->active && changed(stats,b->baseline)) {
        stop(b);
        if (b->scanning) finish_scan(b,"LINK");
        else emit(b,"ERR LINK");
    } else if (b->active && (uint32_t)(now-b->started)>=BRIDGE_RESPONSE_MS) {
        stop(b);
        if (b->scanning) {
            char line[64];
            ++b->missing;
            (void)snprintf(line,sizeof(line),"MISS address=%u reason=TIMEOUT",(unsigned)b->pending.destination);
            emit(b,line);
        } else emit(b,"ERR TIMEOUT");
    }
    if (b->scanning && !b->active) {
        if (b->scan_next>b->scan_end) finish_scan(b,"COMPLETE");
        else if (!begin(b,diagnostic(b,(uint8_t)b->scan_next++,BUS_OP_UID),false,now))
            finish_scan(b,"BUSY");
    }
}
static int nibble(char c)
{
    if (c>='0' && c<='9') return c-'0';
    if (c>='A' && c<='F') return c-'A'+10;
    if (c>='a' && c<='f') return c-'a'+10;
    return -1;
}
static void hex_text(const uint8_t *bytes, unsigned length, char *text)
{
    static const char digits[]="0123456789ABCDEF";
    for (unsigned i=0;i<length;++i) {
        text[2*i]=digits[bytes[i]>>4]; text[2*i+1]=digits[bytes[i]&15];
    }
    text[2*length]='\0';
}
/* Decimal addresses only, no signs, overflow, trailing tokens or broadcasts. */
static bool address(const char **text, uint8_t *value)
{
    unsigned n=0;
    const char *p=*text;
    if (*p<'0' || *p>'9') return false;
    while (*p>='0' && *p<='9') {
        n=n*10u+(unsigned)(*p++-'0');
        if (n>BUS_MAX_ADDRESS) return false;
    }
    if (n==0) return false;
    *value=(uint8_t)n; *text=p;
    return true;
}
static void command(bridge_controller_t *b, uint32_t now)
{
    const char *line=b->line;
    if (strcmp(line,"HELP")==0) {
        emit(b,"CMDS INFO STATS PING/STATUS/INPUTS/UID <addr> SCAN <first> <last> ABORT XFER <48hex>");
    } else if (strcmp(line,"INFO")==0) {
        emit(b,"MICROSMT BRIDGE v2 PROTOCOL=1 GPIO=2 BAUD=9615 MODE=BENCH MOTION=INHIBITED");
    } else if (strcmp(line,"STATS")==0) {
        char out[144];
        (void)snprintf(out,sizeof(out),"STATS framing=%lu overrun=%lu collision=%lu timing=%lu active=%u scan=%u",
            (unsigned long)b->stats.framing,(unsigned long)b->stats.overrun,
            (unsigned long)b->stats.collision,(unsigned long)b->stats.timing,
            (unsigned)b->active,(unsigned)b->scanning);
        emit(b,out);
    } else if (strcmp(line,"ABORT")==0) {
        stop(b);
        if (b->scanning) finish_scan(b,"ABORT");
        emit(b,"OK ABORT");
    } else if (b->active || b->scanning) emit(b,"ERR BUSY");
    else if (strncmp(line,"SCAN ",5)==0) {
        const char *p=line+5; uint8_t first,last;
        if (!address(&p,&first) || *p++!=' ' || !address(&p,&last) || *p || first>last) {
            emit(b,"ERR REQUEST"); return;
        }
        b->scan_next=first; b->scan_end=last; b->found=0; b->missing=0; b->scanning=true;
        emit(b,"SCAN BEGIN");
    } else {
        bus_packet_t q={0}; bool valid=false,raw=false;
        if (strncmp(line,"XFER ",5)==0 && strlen(line)==5+BUS_FRAME_SIZE*2) {
            uint8_t frame[BUS_FRAME_SIZE];
            valid=true;raw=true;
            for (unsigned i=0;i<BUS_FRAME_SIZE;++i) {
                int a=nibble(line[5+2*i]),c=nibble(line[6+2*i]);
                if (a<0 || c<0) { valid=false; break; }
                frame[i]=(uint8_t)((a<<4)|c);
            }
            valid=valid && bus_decode(frame,&q) && bus_is_request(&q) &&
                  q.operation>=BUS_OP_PING && q.operation<=BUS_OP_UID;
        } else {
            static const struct { const char *name; uint8_t op; } ops[]={
                {"PING ",BUS_OP_PING},{"STATUS ",BUS_OP_STATUS},
                {"INPUTS ",BUS_OP_INPUTS},{"UID ",BUS_OP_UID}};
            for (unsigned i=0;i<sizeof(ops)/sizeof(ops[0]);++i) {
                const size_t n=strlen(ops[i].name);
                if (strncmp(line,ops[i].name,n)!=0) continue;
                const char *p=line+n; uint8_t addr;
                if (address(&p,&addr) && !*p) {q=diagnostic(b,addr,ops[i].op);valid=true;}
                break;
            }
        }
        if (!valid) emit(b,"ERR REQUEST");
        else if (!begin(b,q,raw,now)) emit(b,"ERR BUSY");
    }
}
void bridge_input(bridge_controller_t *b, uint8_t ch, uint32_t now)
{
    if (ch=='\n') {
        b->line[b->length]='\0';
        if (b->discard) emit(b,"ERR LINE_TOO_LONG");
        else command(b,now);
        b->length=0;b->discard=false;
    } else if (ch!='\r') {
        if (ch<32 || ch>126 || b->length>=sizeof(b->line)-1) b->discard=true;
        else if (!b->discard) b->line[b->length++]=(char)ch;
    }
}
void bridge_receive(bridge_controller_t *b, uint8_t byte, uint32_t now)
{
    bus_packet_t r;
    if (!b->active || (uint32_t)(now-b->started)>=BRIDGE_RESPONSE_MS ||
        !bus_parser_byte(&b->parser,byte,now,&r) || !bus_matches_reply(&b->pending,&r)) return;
    /* A reply is only accepted after all framing/correlation checks. */
    b->active=false;
    char out[144],hex[BUS_FRAME_SIZE*2+1];
    if (b->raw) {
        uint8_t frame[BUS_FRAME_SIZE];bus_encode(&r,frame);hex_text(frame,BUS_FRAME_SIZE,hex);
        (void)snprintf(out,sizeof(out),"RX %s",hex);
    } else if (b->pending.operation==BUS_OP_UID) {
        hex_text(r.payload,BUS_PAYLOAD_SIZE,hex);
        (void)snprintf(out,sizeof(out),"%s address=%u uid=%s",b->scanning ? "NODE" : "UID",(unsigned)r.source,hex);
        if (b->scanning) ++b->found;
    } else if (b->pending.operation==BUS_OP_PING) {
        if (memcmp(r.payload,b->pending.payload,BUS_PAYLOAD_SIZE)!=0) {emit(b,"ERR PAYLOAD");return;}
        (void)snprintf(out,sizeof(out),"PING address=%u OK",(unsigned)r.source);
    } else if (r.payload[0]!=BUS_RESULT_OK) {
        (void)snprintf(out,sizeof(out),"RESULT address=%u code=%u",(unsigned)r.source,(unsigned)r.payload[0]);
    } else if (b->pending.operation==BUS_OP_STATUS) {
        (void)snprintf(out,sizeof(out),"STATUS address=%u state=%u fault=%u motion_enabled=%u uptime_ms=%lu",
            (unsigned)r.source,(unsigned)r.payload[1],(unsigned)r.payload[2],(unsigned)r.payload[3],
            (unsigned long)bus_get_u32(r.payload+8));
    } else {
        (void)snprintf(out,sizeof(out),"INPUTS address=%u raw=%u",(unsigned)r.source,(unsigned)r.payload[1]);
    }
    emit(b,out);
}
