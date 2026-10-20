// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// CH455 hardware operations only; feeder.c selects which application value to show.

#pragma once

#include <stdint.h>

// Configure GPIO and send the vendor display setup sequence; blocks ~170 ms.
void Display_Init(void);
// Write tens/units to display positions 1/3. Caller must restrict number to 0..99.
// There is no bounds check on the segment lookup table.
void CH455_RefreshNum(uint16_t number);
// Write a raw segment mask to digit 0..3; ignore other digit indices.
// Writes are synchronous and do not report a display ACK/error.
void CH455_SetDisplay(uint8_t digit, uint8_t segments);
