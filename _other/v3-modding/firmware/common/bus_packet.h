#ifndef MICROSMT_BUS_PACKET_H
#define MICROSMT_BUS_PACKET_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define BUS_FRAME_SIZE 24u
#define BUS_PAYLOAD_SIZE 12u
#define BUS_VERSION 1u
#define BUS_REPLY 0x80u
#define BUS_MAX_ADDRESS 247u
#define BUS_OP_PING 0x01u
#define BUS_OP_STATUS 0x02u
#define BUS_OP_INPUTS 0x03u
#define BUS_OP_UID 0x04u
#define BUS_OP_FEED 0x10u
#define BUS_RESULT_OK 0u
#define BUS_RESULT_UNSUPPORTED 2u
#define BUS_RESULT_INHIBITED 3u

typedef struct {
    uint8_t destination, source, operation;
    uint32_t transaction;
    uint8_t payload[BUS_PAYLOAD_SIZE];
} bus_packet_t;
typedef struct { uint8_t data[BUS_FRAME_SIZE]; uint8_t count; uint32_t last_ms; } bus_parser_t;
uint16_t bus_crc16(const uint8_t *data, size_t length);
void bus_encode(const bus_packet_t *packet, uint8_t frame[BUS_FRAME_SIZE]);
bool bus_decode(const uint8_t frame[BUS_FRAME_SIZE], bus_packet_t *packet);
void bus_parser_init(bus_parser_t *parser);
bool bus_parser_byte(bus_parser_t *parser, uint8_t byte, uint32_t now_ms, bus_packet_t *packet);
bool bus_is_request(const bus_packet_t *packet);
bool bus_matches_reply(const bus_packet_t *request, const bus_packet_t *reply);
void bus_put_u32(uint8_t *out, uint32_t value);
uint32_t bus_get_u32(const uint8_t *in);
#endif
