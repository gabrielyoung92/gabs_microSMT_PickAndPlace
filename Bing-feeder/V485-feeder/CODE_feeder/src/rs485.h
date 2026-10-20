// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// Blocking half-duplex transport and vendor command parser; no motor control here.

#pragma once

#include <stdint.h>

// Configure USART1, default to receive and enable byte interrupts.
void RS485_Init(void);
// Send a NUL-terminated string synchronously, then return the transceiver to RX.
// Caller supplies any LF terminator. This is used from main context only.
void RS485_SendString(const char* text);
// Caller must supply two valid output pointers; return 1 writes both values.
// Return 0 for no complete line or invalid input; outputs are unchanged.
// Does not check the current feeder address or whether a motor is busy.
uint8_t RS485_ReadCommand(int* address, int* count);
// Complete valid lines remain queued up to the bounded ring capacity.
// Invalid/overlong/overflowed/error frames are discarded through their LF.

// Shared complete-line transport: excludes LF; preserves all later frames.
uint8_t RS485_ReadLine(char* out, uint16_t outSize);
// Parse the legacy N<id> F<count> grammar without consuming UART input.
uint8_t RS485_ParseFeedCommand(const char* line, int* address, int* count);
// Release the bus and remove UART interrupts before an application jump.
void RS485_DeInit(void);
