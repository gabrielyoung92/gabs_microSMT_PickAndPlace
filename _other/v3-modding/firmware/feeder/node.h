#ifndef MICROSMT_FEEDER_NODE_H
#define MICROSMT_FEEDER_NODE_H
#include "bus_packet.h"
#include "feed_cycle.h"
typedef struct { uint8_t address,uid[12]; feed_cycle_t cycle; } feeder_node_t;
bool feeder_node_init(feeder_node_t *node,uint8_t address,const uint8_t uid[12]);
bool feeder_node_request(feeder_node_t *node,const bus_packet_t *request,
                         uint32_t uptime_ms,uint8_t inputs,bus_packet_t *reply);
#endif
