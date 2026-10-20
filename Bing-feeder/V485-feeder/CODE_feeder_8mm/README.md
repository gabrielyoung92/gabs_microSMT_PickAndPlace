# V485 feeder — 8 mm firmware

> **Original source: [MicroSMT / Bing-feeder](https://github.com/microsmt/Bing-feeder).** This is Gab's independently reorganised copy, prepared with help from ChatGPT. The original MicroSMT designs remain credited to their authors. [Credits and changes](../../../CREDITS.md).

[Back to feeder collection](../README.md)


- **Source:** [V485_feeder_8mm.c](V485_feeder_8mm.c)
- **Format:** plain C using STM32F10x Standard Peripheral Library (SPL).
- **Status:** preserved vendor source, not a complete or verified build project.

## How to build

Read [the shared STM32 build guide](../../STM32-BUILD.txt) for the step-by-step setup, toolchain choices,
missing dependencies and VS Code / PlatformIO limitations.
Build this source as the only application main() in its own matching project.

Required SPL source modules, based on calls in this file:
  stm32f10x_gpio.c, stm32f10x_rcc.c, stm32f10x_exti.c,
  stm32f10x_usart.c, misc.c
Also supply compatible CMSIS headers, startup/vector code,
system_stm32f10x.c, stm32f10x_conf.h and the correct linker memory layout.

## Variant notes

Requires matching USART1, interrupt and system-clock configuration.
The program implements its own SysTick_Handler and software I2C for the
24C02 EEPROM/display-related hardware. Do not add duplicate template IRQ
handlers. Header banner says V26 while its Version line says V25.

## Source integrity

SHA-256: `701c5520c1e80cf2becc244e8f141f8ddb13eaa4589eea2d2843b60acacd016c`
Contents verified unchanged after moving into this folder.
