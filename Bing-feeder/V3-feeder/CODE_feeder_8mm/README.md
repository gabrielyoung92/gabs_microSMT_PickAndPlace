# V3 feeder — 8 mm firmware

> **Original: [MicroSMT / Bing-feeder](https://github.com/microsmt/Bing-feeder).** Reorganised by Gab with ChatGPT. [Credits](../../../CREDITS.md).

[Back to feeder collection](../README.md)


- **Source:** [V3_feeder_8mm_2mm-4mm-pitch.c](V3_feeder_8mm_2mm-4mm-pitch.c)
- **Format:** plain C using STM32F10x Standard Peripheral Library (SPL).
- **Status:** preserved vendor source, not a complete or verified build project.

## How to build

Read [the shared STM32 build guide](../../STM32-BUILD.txt) for the step-by-step setup, toolchain choices,
missing dependencies and VS Code / PlatformIO limitations.
Build this source as the only application main() in its own matching project.

Required SPL source modules, based on calls in this file:
  stm32f10x_gpio.c, stm32f10x_rcc.c, stm32f10x_exti.c,
  stm32f10x_iwdg.c, misc.c
Also supply compatible CMSIS headers, startup/vector code,
system_stm32f10x.c, stm32f10x_conf.h and the correct linker memory layout.

## Variant notes

Timing uses busy-loop delays and an independent watchdog. Confirm clock
settings and optimization when reproducing the vendor build.

## Source integrity

SHA-256: `79106a5f2220f63e880a17c0da1c838362883ed330915017bb2fa5cb4617b62a`
Contents verified unchanged after moving into this folder.

## Supplied binary

[bingfeeder-V3.1-8mm.hex](bingfeeder-V3.1-8mm.hex) is the original vendor image. It has not been
proven to be built from the accompanying C source.
