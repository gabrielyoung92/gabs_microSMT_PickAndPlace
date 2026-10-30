// Feeder-owned reel stock. Existing settings and loader bytes are untouched.
#pragma once
#include <stdint.h>
#define STOCK_BASE 0x40U
#define STOCK_SLOTS 12U
#define STOCK_UNKNOWN UINT16_MAX
#define STOCK_MAX (UINT16_MAX - 1U)
uint8_t Stock_Init(void);
void Stock_Advance(void); // ISR: successful normal feed only; never writes EEPROM.
void Stock_Set(uint16_t remaining); // Main: starts a new quantity baseline.
uint8_t Stock_Flush(void); // Main: one rotating record when dirty.
void Stock_Read(uint32_t* remaining, uint32_t* advances, uint32_t* sequence);
