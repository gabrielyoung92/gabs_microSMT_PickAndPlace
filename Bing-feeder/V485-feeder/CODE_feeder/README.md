# V485 feeder firmware — 8 mm and 12/16/24 mm

> **Original source: [MicroSMT / Bing-feeder](https://github.com/microsmt/Bing-feeder).** This is Gab's independently reorganised copy, prepared with help from ChatGPT. The original MicroSMT designs remain credited to their authors. [Credits and changes](../../../CREDITS.md).

[Back to feeder collection](../README.md)

One plain C PlatformIO project for both supplied V485 variants, converted from STM32F10x SPL to STM32 HAL. Local firmware version **0.3.0**. No Arduino, CubeMX or STM32CubeIDE setup is required.

The application and bootloader share the board, RS485, display and EEPROM drivers. **Every update packet includes its destination feeder ID and a CRC covering that ID.** See [BOOTLOADER.md](BOOTLOADER.md) for installation and uploads.

All `.c` and `.h` files live together in `src/`:

| Files | Purpose |
| --- | --- |
| [main.c](src/main.c) | Short entry point and SysTick handler |
| [bootloader.c](src/bootloader.c) | Separate loader entry point, flash writing and update commands |
| [boot.c](src/boot.c) / [boot.h](src/boot.h) | Shared EEPROM boot record, CRC, image checks and addressed packet framing |
| [config.h](src/config.h) | Version, variant names, wiring, baud, EEPROM locations and timing |
| [board.c](src/board.c) / [board.h](src/board.h) | Clock, GPIO, EXTI setup, motor idle outputs and delays |
| [feeder.c](src/feeder.c) / [feeder.h](src/feeder.h) | Feed control, pulse interrupts, buttons, settings and display selection |
| [rs485.c](src/rs485.c) / [rs485.h](src/rs485.h) | UART interrupt, receive buffer, command parsing and replies |
| [eeprom.c](src/eeprom.c) / [eeprom.h](src/eeprom.h) | 24C02 storage and its software I2C bus |
| [display.c](src/display.c) / [display.h](src/display.h) | CH455 display driver |
| [syscalls.c](src/syscalls.c) | Explicit unsupported file-I/O hooks for the bare-metal C library |
| [stm32f103c8.ld](stm32f103c8.ld) | 56 KB application at 0x08002000, read-only startup tables and fixed identity tag |
| [bootloader.ld](bootloader.ld) | First 8 KB at 0x08000000, reserved for the loader |
| [tools/rs485_upload.py](tools/rs485_upload.py) | Addressed uploads, offline inspection and sequential ID lists |
| [platformio.ini](platformio.ini) | Shared toolchain, two application and two bootloader environments |
| [CHANGELOG.md](CHANGELOG.md) | Local changes and identities of the original sources |

Application state stays private to `feeder.c`, and UART/bus details stay private to their drivers. Both application environments compile the same files; the loader environments select their own entry point and omit feeder control. There are no duplicate driver trees.

## Choose a variant and build

Open **this CODE_feeder folder** in VS Code with the PlatformIO extension. Select the environment in the PlatformIO status bar, or choose **Project Tasks → environment → Build**.

| Environment | Vendor motor behaviour |
| --- | --- |
| `v485_8mm` (default) | Both motors run during a feed and stop at the requested pulse count |
| `v485_12_16_24mm` | PA6/PA7 indexes each feed; PA8/PA12 runs from startup and during normal idle. A timeout fault stops both motors |
| `bootloader_8mm` | Initial SWD loader for 8 mm; both motors always stopped |
| `bootloader_12_16_24mm` | Initial SWD loader for wider firmware; both motors always stopped |

The wider environment covers all three widths because the supplied 12/16/24 mm firmware is one program. It is not a separate build for each width. Choose the matching environment rather than editing `config.h`; PlatformIO sets `FEEDER_WIDE=0` or `1` and the header rejects a missing/invalid selection.

From a PlatformIO terminal in this folder:

```sh
# 8 mm
pio run -e v485_8mm

# 12 / 16 / 24 mm
pio run -e v485_12_16_24mm

# Check all four images (build only)
pio run -e v485_8mm -e v485_12_16_24mm -e bootloader_8mm -e bootloader_12_16_24mm
```

PlatformIO downloads the framework, compiler and startup support automatically. The project selects its local ST-derived linker script for this target. Build outputs are `.pio/build/<environment>/firmware.elf` and `firmware.bin`; the repository's root ignore rules exclude `.pio/`.

The project pins the current packages checked on 20 October 2026:

- [Official ST STM32 platform 20.0.0](https://github.com/platformio/platform-ststm32/releases/tag/v20.0.0).
- [STM32CubeF1 1.8.7](https://github.com/STMicroelectronics/STM32CubeF1/tree/v1.8.7), using STM32 HAL instead of the legacy SPL headers.
- [GNU Arm compiler package 1.140201.0](https://registry.platformio.org/tools/platformio/toolchain-gccarmnoneeabi), GCC 14.2.1. It is explicitly selected because the platform's default Cube compiler is older.

Versions are pinned so another build uses the same dependencies. See the [PlatformIO STM32Cube framework documentation](https://docs.platformio.org/en/latest/frameworks/stm32cube.html).

## Target and clock

The `bluepill_f103c8` profile supplies an **STM32F103C8**, **64 KB flash**, **20 KB RAM** build. This is an MCU profile, not a claim that the feeder PCB is a Blue Pill.

The port assumes an **8 MHz external crystal**, configured as HSE → PLL ×9 → **72 MHz CPU**, APB1 36 MHz and APB2 72 MHz. `HSE_VALUE` in `platformio.ini` and the PLL setup in `board.c` must agree with the actual oscillator. Microsecond delays use the Cortex-M3 cycle counter; SysTick supplies both HAL and application millisecond timing.

The **bootloader starts at 0x08000000 (8 KB)**; the **application starts at 0x08002000 (56 KB)**. EEPROM holds boot metadata, so no last flash page is reserved. Application builds relocate their interrupt vectors accordingly. Install the loader once with ST-Link, then install/update the application through addressed RS485 uploads. Old unrelocated binaries are incompatible. The [installation guide](BOOTLOADER.md) explains the two steps. Physical chip/crystal and hardware operation remain unverified; nothing has been flashed.

## I/O and operation

The supplied wiring is retained in [src/config.h](src/config.h):

| Function | Pins / settings |
| --- | --- |
| LED | PB5, active low |
| Index motor | PA6 / PA7; both high stops the motor |
| Peel motor | PA8 / PA12; 8 mm stops between feeds; wider variant keeps PA12 high / PA8 low |
| Buttons | PA2 increment/manual feed, PA4 decrement; active low |
| Feed pulse counter | PA3 rising edge, EXTI3 |
| External feed trigger | PB6 rising edge, EXTI9_5 |
| RS485 | USART1 PA9 TX / PA10 RX; PA1 direction; 9600 baud, 8N1 |
| 24C02 EEPROM | PB15 SCL / PB14 SDA; address at byte 0, default count at byte 1; boot state at 0x1F, metadata at 0x20–0x33 |
| CH455 display | PB12 clock / PB13 data |

Floating inputs and EEPROM open-drain signals depend on the board's external bias/pull-ups. Interrupt pin moves also require matching handlers in `feeder.c` and routing in `board.c`; changing only a header pin is insufficient. USART1 uses PA9/PA10 without remapping.

Commands are `N<address> F<count>` followed by LF (or CRLF), with address/count 0–99 and at least one space/tab between fields. Signs, extra fields and trailing garbage are rejected. `F0` selects the stored default count, which must be **1–99**; an old EEPROM count of zero is replaced with the default of 1.

A matching command receives `Busy` when another feed is reserved/running or a timeout fault is latched. Otherwise it reserves the count, replies `OK`, then starts the motor. External/manual triggers cannot replace that reserved count during the reply delay. **OK means accepted, not feed completed**. Startup prints the address, local version and selected variant, for example `Addr:0 v0.3.0 8mm` or `Addr:0 v0.3.0 12-16-24mm`.

Hold PA4 for three seconds to enter/exit address adjustment; hold PA2 for three seconds to enter/exit default-count adjustment. Short presses of PA2/PA4 increase/decrease that setting. In normal mode, a short PA2 press triggers a feed. Settings remain in the same EEPROM locations as the supplied source. Address adjustment allows 0–99; count adjustment stops at 1. Feed inputs stay inhibited until startup flashes, version output and final idle writes finish.

Monitoring requires an external RS485 adapter; ST-Link alone is not a serial connection. Select its port in PlatformIO and use 9600 baud / LF.

## Feed timeout and recovery

`FEED_TIMEOUT_MS` in [src/config.h](src/config.h) defaults to **10,000 ms**, measured from motor start across the entire feed. SysTick enforces it even when main is occupied with button/LED feedback. It is a total deadline, not a timer that resets on each pulse.

On timeout, **both motor channels stop**, including the wider variant's continuous peel motor. The fault stays latched until reset/power cycle: new serial commands receive `Busy`, and manual/external triggers cannot restart a motor. The main loop displays **EE** with the LED on when it next services the display. Inspect the feeder before resetting it.

The 10-second setting is an initial software limit, not a measured safe time for the hardware. Check it against the slowest intended load/count during physical validation. Normal pulse-count completion still leaves the wider variant's peel motor running.

## Receive queue and display ownership

The UART ISR commits only complete clean lines, up to **95 characters before LF** (including any CR). The 256-byte ring holds at most **255 queued bytes**, including LF terminators. Main consumes one command per pass and preserves later frames. A partial line is never available for parsing.

NUL, UART errors, excessive line length or insufficient ring space reject the affected line through its next clean LF. Previously committed frames stay queued; overflow cannot expose a valid-looking fragment as a new feed command. Capacity remains bounded, so the host must pace requests and wait for the reply rather than stream an unlimited burst.

All CH455 transfers run in main context. Count/trigger/SysTick handlers update motor state and request a refresh; they never call the display driver. Refresh requests arriving during a transfer remain pending for the next pass.

## Validation and remaining limits

All four environments build without compiler/linker warnings. Linked images were checked for the separate flash/vector bases, RAM/stack layout, fixed image identity, version strings and application interrupt handlers. Toolchain pins are unchanged; version 0.3.0 introduces the bootloader/application memory split. Current sizes and update checks are recorded in the changelog.

Temporary actual-source checks with address/undefined-behaviour sanitizers covered command/trigger interleaving during ACK turnaround, startup trigger inhibition, first-pulse capture, zero-count migration/adjustment, display preemption, timeout fault latching during blocked main and timer wraparound. UART checks covered queued frames, incomplete/overlong/NUL/error input, numeric bounds, CRLF, ring exhaustion/recovery and repeated ring wraparound. These used simulated GPIO, interrupts and time, not physical hardware. No tests folder was added.

Button/EEPROM feedback still blocks main-loop command handling, but count interrupts and the feed deadline keep running. Legacy **feed commands** have no transaction IDs, completion replies or retry deduplication; do not automatically resend a feed merely because an ACK was lost. The separate firmware protocol supports chunk retry/readback and final CRC verification. EEPROM writes now check ACKs and read back each byte, although the existing button UI does not report a settings-save failure. Display acknowledgements remain unverified, and the software deadline does not replace hardware protection against CPU/interrupt failure. MCU/crystal assumptions, bus timing, motor operation and display wiring remain physically unverified.

Version 0.1.1's explicit unsupported file-I/O hooks and read-only flash startup tables remain in place; no warning suppression is used. See [GNU ld output section attributes](https://sourceware.org/binutils/docs/ld/Output-Section-Type.html) for the `READONLY` setting.

### C-library file operations

`snprintf` formats the startup text in memory; command parsing uses a bounded decimal parser in `rs485.c`. Serial traffic uses that module's dedicated driver. This firmware does not provide a filesystem or a `printf` console. The `_read`, `_write`, `_close` and `_lseek` hooks in `syscalls.c` explicitly return failure with `errno = ENOSYS`; they do not claim that unsupported I/O succeeded. These hooks resolve the library references that previously selected warning-producing generic stubs. Unused functions are still removed by linker garbage collection.
