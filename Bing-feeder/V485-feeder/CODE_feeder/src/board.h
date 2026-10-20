// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// Board support used by the application and bit-banged peripheral drivers.

#pragma once

#include "stm32f1xx_hal.h"

// Call first: initialise HAL, motor levels, clocks, cycle counter and 1 ms tick.
// The wider APPLICATION starts its peel motor; bootloader stops both motors.
void Board_Init(void);
// Configure one or more pins on an already-clocked port, without internal pulls.
void Board_ConfigurePin(GPIO_TypeDef* port, uint16_t pins, uint32_t mode);
// Enable rising-edge feed/count inputs after application settings are valid.
void Board_EnableFeedInterrupts(void);
// Stop the indexed motor; stop/continue the peel motor according to the variant.
void Board_MotorIdle(void);
// Setup failure stops BOTH motors, including in the continuous-peel variant.
void Board_ErrorHandler(void);
// Blocking wait; needs the SysTick interrupt to run. Use from main context.
void delay_ms(uint32_t ms);
// Short busy-wait for bus edges, using the cycle counter enabled by Board_Init.
void delay_us(uint32_t us);
