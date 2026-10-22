# V3 feeder — 12/16/24 mm firmware

> Designs and original files by [MicroSMT](https://github.com/microsmt/Bing-feeder). [Credits and local changes](../../../CREDITS.md).

[Back to feeder collection](../README.md)

- **Source:** [V3_feeder_12-16-24mm.c](V3_feeder_12-16-24mm.c)
- **Code:** C using the STM32F10x Standard Peripheral Library (SPL).

This is MicroSMT’s original source. It needs a complete STM32 project around it before it can be built; this folder isn’t ready to compile on its own.

## How to build

Start with [the STM32 build guide](../../STM32-BUILD.txt). It covers the missing files, toolchain choices and what VS Code/PlatformIO can do with this source. Use a separate project for this variant, with this file as its only application `main()`.

The calls in this file need these SPL modules:

```text
stm32f10x_gpio.c, stm32f10x_rcc.c, stm32f10x_exti.c,
  stm32f10x_iwdg.c, stm32f10x_flash.c, misc.c
```

You also need matching CMSIS headers, startup/vector code, `system_stm32f10x.c`, `stm32f10x_conf.h` and a linker script for the actual MCU.

## Variant notes

`FLASH_ADDR` is `0x08010100`, beyond the flash range of a 64 KB STM32F103C8. Check the actual MCU and reserve a suitable erase page in the linker script before using the settings-storage code. The source has been left unchanged. Its busy-loop delays and independent watchdog also depend on the clock and compiler settings.

## Source integrity

SHA-256: `2e63b503abdb48a2a5713034013a078fbc34eeb78049a0be5471b3d7092015e9`
The file contents were unchanged when moved into this folder.
