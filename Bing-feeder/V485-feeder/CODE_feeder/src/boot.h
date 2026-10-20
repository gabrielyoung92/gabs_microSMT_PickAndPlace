// Gab's local V485 boot/update support; original MicroSMT credit in README.md.
#pragma once
#include <stdint.h>
#include <stddef.h>

// Must agree with both linker scripts and application VECT_TAB_OFFSET.
#define BOOT_APP_START 0x08002000U
#define BOOT_FLASH_END 0x08010000U
#define BOOT_APP_MAX (BOOT_FLASH_END - BOOT_APP_START)
#define BOOT_PAGE_SIZE 1024U
#define BOOT_TAG_OFFSET 0x200U
#define BOOT_CHUNK_SIZE 32U
// Bytes 0/1 remain the vendor feeder ID/default count. No flash config page.
#define BOOT_STATE_ADDR 0x1FU
#define BOOT_RECORD_ADDR 0x20U
#define BOOT_VALID 0xA5U
#define BOOT_REQUESTED 0x5AU
#define BOOT_WRITING 0x00U

// Explicit fixed-width, little-endian STM32 record; checksum covers first 16 B.
typedef struct {
    uint32_t magic, variant, size, imageCrc, recordCrc;
} BootRecord;
_Static_assert(sizeof(BootRecord) == 20, "EEPROM boot record layout changed");
uint32_t Boot_Crc32(const void* data, size_t size);
uint8_t Boot_ReadRecord(BootRecord* record, uint8_t* state);
uint8_t Boot_WriteState(uint8_t state);
uint8_t Boot_SaveRecord(const BootRecord* record);
uint8_t Boot_ImageValid(const BootRecord* record);
// ID is read separately from metadata. Blank EEPROM means commissioning ID 0;
// failed I2C is never treated as a usable destination.
uint8_t Boot_ReadId(uint8_t* id);
// Every update request/reply is Bdd <body> <CRC32> LF. CRC covers ASCII prefix
// AND destination, excluding the space before the final eight hex digits.
// Wrong destination, malformed input or CRC error: ignore, never reply or write.
char* Boot_DecodePacket(char* line, uint8_t id);
void Boot_Reply(uint8_t id, const char* status, const uint32_t* values, uint8_t count);
// Parse EXACTLY eight hex digits, advancing only on success.
uint8_t Boot_ParseHex(const char** text, uint32_t* value);
