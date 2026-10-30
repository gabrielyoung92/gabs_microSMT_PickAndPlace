// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// Board support used by the application and bit-banged peripheral drivers.

#pragma once

#include "stm32f1xx_hal.h"

// Call first: initialise HAL, motor levels, clocks, cycle counter and 1 ms tick.
// Both motors remain stopped until application startup has completed.
void Board_Init(void);
// Application main-loop progress only; never refresh from an interrupt.
void Board_WatchdogFeed(void);
// Reset status captured by the application before clearing sticky RCC flags.
uint32_t Board_ResetFlags(void);
// Configure one or more pins on an already-clocked port, without internal pulls.
void Board_ConfigurePin(GPIO_TypeDef* port, uint16_t pins, uint32_t mode);
// Enable rising-edge feed/count inputs after application settings are valid.
void Board_EnableFeedInterrupts(void);
// Stop both motors. Application tension control owns subsequent peel starts.
void Board_MotorIdle(void);
// Setup failure stops both motors; the application watchdog then resets us.
void Board_ErrorHandler(void);
// Blocking wait; needs the SysTick interrupt to run. Use from main context.
void delay_ms(uint32_t ms);
// Short busy-wait for bus edges, using the cycle counter enabled by Board_Init.
void delay_us(uint32_t us);
