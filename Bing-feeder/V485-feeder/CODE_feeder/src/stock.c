// Local stock persistence for the MicroSMT-derived feeder application.
#include "stock.h"
#include "eeprom.h"
#include "boot.h"
#include <stddef.h>

typedef struct {
    uint32_t sequence, advances;
    uint16_t remaining, marker;
    uint32_t crc;
} StockRecord;
_Static_assert(sizeof(StockRecord) == 16, "Stock EEPROM record must be 16 bytes");
_Static_assert(STOCK_BASE + STOCK_SLOTS * sizeof(StockRecord) == 256, "Stock region bounds");
static volatile uint16_t remaining = STOCK_UNKNOWN;
static volatile uint32_t advances;
static uint32_t sequence;
static int8_t lastSlot = -1;
static volatile uint8_t dirty;

uint8_t Stock_Init(void) {
    remaining = STOCK_UNKNOWN; advances = sequence = dirty = 0; lastSlot = -1;
    for (uint8_t slot = 0; slot < STOCK_SLOTS; slot++) {
        StockRecord record;
        for (uint8_t i = 0; i < sizeof(record); i++)
            if (!EEPROM_ReadChecked(STOCK_BASE + slot * sizeof(record) + i, ((uint8_t*)&record) + i)) return 0;
        if (record.marker != 0x5354U || record.crc != Boot_Crc32(&record, offsetof(StockRecord, crc))) continue;
        if (lastSlot < 0 || (int32_t)(record.sequence - sequence) > 0) {
            sequence = record.sequence; advances = record.advances;
            remaining = record.remaining; lastSlot = slot;
        }
    }
    return 1;
}

void Stock_Advance(void) {
    if (remaining != STOCK_UNKNOWN && remaining) remaining--;
    if (advances != UINT32_MAX) advances++;
    dirty = 1;
}

void Stock_Set(uint16_t quantity) {
    remaining = quantity; advances = 0; dirty = 1;
}

uint8_t Stock_Flush(void) {
    if (!dirty) return 1;
    StockRecord record = {sequence + 1U, advances, remaining, 0x5354U, 0};
    record.crc = Boot_Crc32(&record, offsetof(StockRecord, crc));
    uint8_t slot = (lastSlot + 1) % STOCK_SLOTS;
    // CRC is written last. A torn record leaves the preceding valid slot.
    for (uint8_t i = 0; i < sizeof(record); i++)
        if (!EEPROM_WriteByte(STOCK_BASE + slot * sizeof(record) + i, ((uint8_t*)&record)[i])) return 0;
    lastSlot = slot; sequence = record.sequence; dirty = 0;
    return 1;
}

void Stock_Read(uint32_t* quantity, uint32_t* completed, uint32_t* savedSequence) {
    *quantity = remaining; *completed = advances; *savedSequence = sequence;
}
