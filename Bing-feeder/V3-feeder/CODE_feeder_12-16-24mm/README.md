# V3 feeder — 12/16/24 mm firmware

> **Original: [MicroSMT / Bing-feeder](https://github.com/microsmt/Bing-feeder).** [Credits and local changes](../../../CREDITS.md).

[Back to feeder collection](../README.md)


- **Source:** [V3_feeder_12-16-24mm.c](V3_feeder_12-16-24mm.c)
- **Format:** plain C using STM32F10x Standard Peripheral Library (SPL).
- **Status:** preserved vendor source, not a complete or verified build project.

## How to build

Read [the shared STM32 build guide](../../STM32-BUILD.txt) for the step-by-step setup, toolchain choices,
missing dependencies and VS Code / PlatformIO limitations.
Build this source as the only application main() in its own matching project.

Required SPL source modules, based on calls in this file:
  stm32f10x_gpio.c, stm32f10x_rcc.c, stm32f10x_exti.c,
  stm32f10x_iwdg.c, stm32f10x_flash.c, misc.c
Also supply compatible CMSIS headers, startup/vector code,
system_stm32f10x.c, stm32f10x_conf.h and the correct linker memory layout.

## Variant notes

FLASH_ADDR is 0x08010100: outside the specified flash range of a 64 KB
STM32F103C8. Confirm the MCU and reserve an appropriate erase page in the
linker layout before using this persistence code. Source is unchanged.
Timing also uses busy-loop delays and an independent watchdog.

## Source integrity

SHA-256: `2e63b503abdb48a2a5713034013a078fbc34eeb78049a0be5471b3d7092015e9`
Contents verified unchanged after moving into this folder.
