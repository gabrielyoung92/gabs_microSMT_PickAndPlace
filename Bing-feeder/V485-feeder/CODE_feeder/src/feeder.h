// Derived from MicroSMT/Bing-feeder V485 firmware. Local HAL/PlatformIO port.
// Original authors retain credit; see README.md and CHANGELOG.md.
//
// Application entry points. Feed/button/display state stays private in feeder.c.

#pragma once

// After board/EEPROM/display init: load settings, enable inputs and show startup.
// Feed inputs remain inhibited until all startup output/idle writes finish.
void Feeder_Init(void);
// One main-loop pass: poll buttons and commands, including blocking UI delays.
void Feeder_Run(void);
// SysTick service: manual-trigger countdown and hard feed deadline; never blocks.
void Feeder_Tick(void);
