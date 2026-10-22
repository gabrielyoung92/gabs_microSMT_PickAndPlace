// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// Single-byte 24C02 access. The application owns the meaning of stored offsets.

#pragma once

#include <stdint.h>

// Release the open-drain bus; requires Board_Init and external pull-ups.
void EEPROM_Init(void);
// Checked read distinguishes bus failure from a stored 0xFF.
uint8_t EEPROM_ReadChecked(uint8_t address, uint8_t* value);
// Check every ACK, wait 5 ms, then verify by readback. Return 1 on success.
// Existing application callers may ignore the result; boot metadata must not.
uint8_t EEPROM_WriteByte(uint8_t address, uint8_t value);
