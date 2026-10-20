#include "node.h"
#include <string.h>
bool feeder_node_init(feeder_node_t *n,uint8_t address,const uint8_t uid[12])
{
    if (address<1 || address>BUS_MAX_ADDRESS) return false;
    memset(n,0,sizeof(*n)); n->address=address; memcpy(n->uid,uid,12);
    feed_cycle_init(&n->cycle); return true;
}
bool feeder_node_request(feeder_node_t *n,const bus_packet_t *q,uint32_t now,uint8_t inputs,bus_packet_t *r)
{
    if (!bus_is_request(q) || q->destination!=n->address) return false;
    *r=(bus_packet_t){.destination=0,.source=n->address,
        .operation=(uint8_t)(q->operation|BUS_REPLY),.transaction=q->transaction};
    switch (q->operation) {
    case BUS_OP_PING: memcpy(r->payload,q->payload,12); break;
    case BUS_OP_UID: memcpy(r->payload,n->uid,12); break;
    case BUS_OP_INPUTS: r->payload[1]=inputs; break;
    case BUS_OP_STATUS:
        feed_cycle_poll(&n->cycle,now);
        r->payload[1]=(uint8_t)n->cycle.state;
        r->payload[2]=(uint8_t)n->cycle.error;
        r->payload[3]=0; /* Motion capability deliberately absent in this build. */
        bus_put_u32(r->payload+8,now); break;
    case BUS_OP_FEED: r->payload[0]=BUS_RESULT_INHIBITED; break;
    default: r->payload[0]=BUS_RESULT_UNSUPPORTED; break;
    }
    return true;
}
