// Shared boot metadata, image validation and addressed packet framing.
// Local extension to the MicroSMT-derived V485 application. See BOOTLOADER.md.
#include "boot.h"
#include "config.h"
#include "eeprom.h"
#include "rs485.h"
#include "board.h"
#include <string.h>

#define RECORD_MAGIC 0x31423556U  // Little-endian "V5B1": metadata format 1.

// Software IEEE CRC32, identical to Python/zlib. No MCU peripheral ownership.
uint32_t Boot_Crc32(const void* data, size_t size) {
    const uint8_t* bytes = data;
    uint32_t crc = 0xFFFFFFFFU;
    while (size--) {
        crc ^= *bytes++;
        for (uint8_t bit = 0; bit < 8; bit++)
            crc = (crc >> 1) ^ (0xEDB88320U & (0U - (crc & 1U)));
    }
    return ~crc;
}

// These are the only EEPROM offsets modified by the updater; ID/count survive.
uint8_t Boot_WriteState(uint8_t state) {
    return EEPROM_WriteByte(BOOT_STATE_ADDR, state);
}

uint8_t Boot_ReadId(uint8_t* id) {
    uint8_t saved;
    if (!EEPROM_ReadChecked(EEPROM_DATA_ADDR, &saved)) return 0;
    if (saved == 0xFFU) saved = DEFAULT_ADDRESS;
    if (saved > VALUE_MAX) return 0;
    *id = saved;
    return 1;
}

// A record alone does not authorise boot: caller also checks state and FLASH.
uint8_t Boot_ReadRecord(BootRecord* record, uint8_t* state) {
    if (!EEPROM_ReadChecked(BOOT_STATE_ADDR, state)) return 0;
    uint8_t* bytes = (uint8_t*)record;
    for (uint8_t i = 0; i < sizeof(*record); i++)
        if (!EEPROM_ReadChecked(BOOT_RECORD_ADDR + i, bytes + i)) return 0;
    return record->magic == RECORD_MAGIC &&
           record->recordCrc == Boot_Crc32(record, offsetof(BootRecord, recordCrc));
}

// Caller must have invalidated the marker BEFORE erasing flash. Save all bytes
// with checked writes; write VALID last only after the image was verified.
uint8_t Boot_SaveRecord(const BootRecord* source) {
    BootRecord record = *source;
    record.magic = RECORD_MAGIC;
    record.recordCrc = Boot_Crc32(&record, offsetof(BootRecord, recordCrc));
    const uint8_t* bytes = (const uint8_t*)&record;
    for (uint8_t i = 0; i < sizeof(record); i++)
        if (!EEPROM_WriteByte(BOOT_RECORD_ADDR + i, bytes[i])) return 0;
    return Boot_WriteState(BOOT_VALID);
}

// Reject wrong width/base, truncated images, invalid stack/reset vectors and
// all CRC mismatches. A partial/foreign application can never be jumped into.
uint8_t Boot_ImageValid(const BootRecord* record) {
    if (record->variant != FEEDER_VARIANT_ID ||
        record->size < BOOT_TAG_OFFSET + 16U || record->size > BOOT_APP_MAX) return 0;
    const uint32_t* vectors = (const uint32_t*)BOOT_APP_START;
    uint32_t stack = vectors[0], reset = vectors[1];
    if (stack <= 0x20000000U || stack > 0x20005000U || (stack & 7U) ||
        !(reset & 1U) || (reset & ~1U) < BOOT_APP_START ||
        (reset & ~1U) >= BOOT_APP_START + record->size) return 0;
    const uint32_t* tag = (const uint32_t*)(BOOT_APP_START + BOOT_TAG_OFFSET);
    if (memcmp(tag, "V485APP", 8) || tag[2] != record->variant ||
        tag[3] != BOOT_APP_START) return 0;
    return Boot_Crc32((const void*)BOOT_APP_START, record->size) == record->imageCrc;
}

// Bounded parser: test each byte before advancing, including short strings.
uint8_t Boot_ParseHex(const char** text, uint32_t* value) {
    const char* cursor = *text;
    uint32_t result = 0;
    for (uint8_t i = 0; i < 8; i++) {
        char ch = cursor[i];
        uint8_t digit;
        if (ch >= '0' && ch <= '9') digit = ch - '0';
        else if (ch >= 'A' && ch <= 'F') digit = ch - 'A' + 10;
        else if (ch >= 'a' && ch <= 'f') digit = ch - 'a' + 10;
        else return 0;
        result = (result << 4) | digit;
    }
    *text += 8;
    *value = result;
    return 1;
}

static void HexText(char* out, uint32_t value) {
    const char digits[] = "0123456789ABCDEF";
    for (int i = 7; i >= 0; i--) { out[i] = digits[value & 15U]; value >>= 4; }
}

// The prefix ID is checked before any response or state change. CRC protects
// the destination as well as the payload, so a damaged ID cannot redirect data.
char* Boot_DecodePacket(char* line, uint8_t id) {
    size_t length = strlen(line);
    if (length && line[length - 1] == '\r') line[--length] = 0;
    if (length < 14 || line[0] != 'B' ||
        line[1] != '0' + id / 10 || line[2] != '0' + id % 10 || line[3] != ' ') return NULL;
    char* separator = line + length - 9;
    const char* checksum = separator + 1;
    uint32_t expected;
    if (*separator != ' ' || !Boot_ParseHex(&checksum, &expected) || *checksum ||
        Boot_Crc32(line, (size_t)(separator - line)) != expected) return NULL;
    *separator = 0;
    return line + 4;
}

// At most three 32-bit values. Avoid printf in the small bootloader image.
void Boot_Reply(uint8_t id, const char* status, const uint32_t* values, uint8_t count) {
    char line[80];
    size_t size = strlen(status);
    if (id > VALUE_MAX || size > 30 || count > 3) return;
    line[0] = 'B'; line[1] = '0' + id / 10; line[2] = '0' + id % 10; line[3] = ' ';
    memcpy(line + 4, status, size);
    size += 4;
    for (uint8_t i = 0; i < count; i++) {
        line[size++] = ' ';
        HexText(line + size, values[i]); size += 8;
    }
    uint32_t crc = Boot_Crc32(line, size);
    line[size++] = ' ';
    HexText(line + size, crc); size += 8;
    line[size++] = '\n'; line[size] = 0;
    delay_ms(ACK_TURNAROUND_MS);
    RS485_SendString(line);
}
