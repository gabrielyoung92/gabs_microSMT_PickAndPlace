# V3 feeder — 8 mm firmware

> Designs and original files by [MicroSMT](https://github.com/microsmt/Bing-feeder). [Credits and local changes](../../../CREDITS.md).

[Back to feeder collection](../README.md)

- **Source:** [V3_feeder_8mm_2mm-4mm-pitch.c](V3_feeder_8mm_2mm-4mm-pitch.c)
- **Code:** C using the STM32F10x Standard Peripheral Library (SPL).

This is MicroSMT’s original source. It needs a complete STM32 project around it before it can be built; this folder isn’t ready to compile on its own.

## How to build

Start with [the STM32 build guide](../../STM32-BUILD.txt). It covers the missing files, toolchain choices and what VS Code/PlatformIO can do with this source. Use a separate project for this variant, with this file as its only application `main()`.

The calls in this file need these SPL modules:

```text
stm32f10x_gpio.c, stm32f10x_rcc.c, stm32f10x_exti.c,
  stm32f10x_iwdg.c, misc.c
```

You also need matching CMSIS headers, startup/vector code, `system_stm32f10x.c`, `stm32f10x_conf.h` and a linker script for the actual MCU.

## Variant notes

The code uses busy-loop delays and an independent watchdog. Check the clock and compiler optimisation settings when rebuilding it.

## Source integrity

SHA-256: `79106a5f2220f63e880a17c0da1c838362883ed330915017bb2fa5cb4617b62a`
The file contents were unchanged when moved into this folder.

## Supplied binary

[bingfeeder-V3.1-8mm.hex](bingfeeder-V3.1-8mm.hex) is MicroSMT’s original image. We haven’t established whether it was built from this C file.
