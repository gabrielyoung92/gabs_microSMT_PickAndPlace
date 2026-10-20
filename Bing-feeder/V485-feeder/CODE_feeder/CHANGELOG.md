# Changelog

Changes here are local adaptations, prepared with ChatGPT assistance, of the [MicroSMT / Bing-feeder](https://github.com/microsmt/Bing-feeder) firmware.

## 0.3.0 — 2026-10-20

- Added an 8 KB bootloader and 56 KB relocated application, in the same PlatformIO project. New `bootloader_8mm` and `bootloader_12_16_24mm` environments use shared board/RS485/CH455/EEPROM/CRC modules and keep both motors stopped. Normal boot checks the image and jumps without a listen window; requested/invalid/incomplete updates wait in recovery.
- Made every firmware command/data packet destination-ID addressed, with CRC32 covering both ID and payload. Preserve feeder ID/default count at EEPROM bytes 0/1. Separate checked EEPROM boot flag/record replaces the proposed last-flash-page metadata reservation.
- Added addressed app INFO/BOOT commands, atomic idle shutdown, verified request flag and reset. Running/reserved feeds reject BOOT; faults can enter the loader. Failed EEPROM writes leave motors stopped and do not reset into an unconfirmed update request.
- Added bounded page erase, halfword programming/readback, retry-safe BEGIN/DATA, full-image CRC/vector/width/identity validation, and valid-marker-last metadata commit. Reset during an upload requires restarting the transfer. This is a single application slot, without A/B rollback or broadcast programming.
- Added a Python/pyserial uploader with explicit ID or sequential ID list, width/layout validation, retry handling, lost-final-ACK confirmation, offline inspection and a small retained `--self-check`. Application Upload uses this tool; initial loader Upload uses ST-Link. Destination defaults to `REQUIRED`, preventing accidental selection of ID 0.
- Checked EEPROM bus idle, every write ACK and byte readback. Expanded shared UART framing to 95 characters / 255 queued bytes for update packets. Legacy feeds retain their parsing and motor behaviour.
- Updated version string, commented PlatformIO/source settings, linker notices, build/installation/protocol documentation and upstream attribution. No tests folder, hardware upload, commit or push.

### Validation

All four environments build without compiler/linker warnings:

| Environment | Flash used / allocation | Static RAM / 20,480 bytes |
| --- | --- | --- |
| `v485_8mm` | 10,344 / 57,344 bytes | 836 bytes |
| `v485_12_16_24mm` | 10,352 / 57,344 bytes | 836 bytes |
| `bootloader_8mm` | 5,860 / 8,192 bytes | 832 bytes |
| `bootloader_12_16_24mm` | 5,860 / 8,192 bytes | 832 bytes |

PlatformIO flash counts sum allocated data/code sections; application BIN files also include fixed-offset padding (10,888 / 10,896 bytes). Loader BIN files are 6,144 bytes including padding. Static RAM excludes runtime stack/heap. Confirmed loader/application vectors at 0x08000000/0x08002000, stack at 0x20005000, fixed identity tags and no RWX load segments.

Temporary actual-source checks with address/undefined-behaviour sanitizers cover all prior feeder regressions, BOOT idle/busy/reserved/fault/EEPROM-error handling, destination CRC checks, wrong-ID silence, metadata write failure points, protected flash boundaries, duplicate requests/chunks, transfer restart, odd final bytes, corruption and width/vector/tag rejection. Actual C loader/Python uploader integration passes for both variants with lost BEGIN/DATA/DONE replies and stale ACKs. Offline image inspections and retained uploader self-check pass. Hardware, boot timing and physical update/brownout recovery remain unverified.

## 0.2.0 — 2026-10-20

Fixed the seven findings from the V485 application review, for both feeder environments:

- **Command/start race:** introduced atomic idle → reserved → running transitions. Reserve the resolved count before the RS485 reply delay, and arm counting before driving the motor. Manual/external triggers use the same reservation and cannot overwrite an accepted command.
- **Startup stuck Busy:** keep feed input requests inhibited until settings, startup flashes, version output and final idle writes have completed; enable the inputs last.
- **Malformed frames:** publish only full bounded lines. Reject NUL, UART-error, overlong or overflowed frames through their next clean LF. Replaced `sscanf` with bounded decimal parsing that rejects signs, missing separators, out-of-range values and trailing garbage.
- **Missing-pulse/runaway feed:** added a configurable total feed deadline of 10 seconds, enforced in SysTick even during blocked main-loop feedback. Timeout stops both motor channels, latches the fault until reset and inhibits further feed requests. Main displays EE; addressed serial requests return Busy while faulted. Validate the deadline on the real mechanism.
- **Dropped queued commands:** consume exactly one frame without flushing the next or another feeder's traffic. A committed queue head and separate producer cursor preserve old complete frames if a new frame is rejected. Capacity remains 63 bytes including line terminators; the host must pace requests.
- **Display interrupt overlap:** all CH455 transfers now run in main context. Interrupts only request a refresh; a request during a display transfer remains pending for another pass.
- **Zero stored count:** restrict stored/default count adjustment to 1–99, migrate zero/invalid EEPROM counts to the default of 1, and retain F0 as “use the positive stored count.” Reject an invalid resolved count without starting a motor.
- Removed the unnecessary 120 ms main-loop blanking delay. Preserved normal wider-variant continuous peel operation; only a fault stops both motors.
- Added/updated module, API, timing and configuration comments. Firmware version is 0.2.0; the earlier comments-only pass did not change the 0.1.1 binaries.

### Validation

Both pinned PlatformIO environments build without compiler/linker warnings. Temporary checks of the actual C sources passed with address/undefined-behaviour sanitizers, including all reproduced review cases, first-pulse capture, deferred display refresh, timer wraparound, timeout while main is blocked, fault lockout, EEPROM zero migration and thousands of receive-ring wraps. UART errors and buffer exhaustion reject the damaged frame and recover on a clean boundary without losing previously committed frames. No project tests folder was added.

| Environment | Flash / 65,536 bytes | Static RAM / 20,480 bytes |
| --- | --- | --- |
| `v485_8mm` | 9,168 bytes | 644 bytes |
| `v485_12_16_24mm` | 9,176 bytes | 644 bytes |

Static RAM excludes runtime stack/heap use. Verified flash at 0x08000000, initial stack at 0x20005000, application IRQ vectors, version/variant strings and absence of writable/executable load segments. Checks use simulated hardware; the timeout setting and physical operation remain unverified. No bootloader/updater, hardware upload, commit or push is included.

## 0.1.1 — 2026-10-20

- Resolved the GCC 14 bare-metal linker warnings without warning-suppression flags.
- Added `src/syscalls.c` with explicit `_read`, `_write`, `_close` and `_lseek` hooks. File I/O remains unsupported: each returns failure with `errno = ENOSYS`. Buffer-based `snprintf`/`sscanf` and the separate RS485 driver are unchanged.
- Selected a local ST-derived `stm32f103c8.ld`, retaining its 64 KB flash / 20 KB RAM layout, startup symbols and heap/stack reservations. Marked preinit/init/fini pointer tables `READONLY` so the flash load segment is RX rather than RWX. Retained ST attribution and BSD-3-Clause terms in the script.
- Updated the firmware version string to `0.1.1` and the build documentation.
- Both environments built with no compiler/linker warnings. Flash/static RAM use remains **11,672 / 640 bytes** for 8 mm and **11,676 / 640 bytes** for 12/16/24 mm. Checked both images' LOAD flags, vector addresses and startup table flags, plus temporary unsupported-I/O and simulated feeder checks. No hardware was flashed.

## 0.1.0 — 2026-10-20

- Combined the supplied V485 8 mm and 12/16/24 mm programs into one `CODE_feeder` PlatformIO project. Replaced the two old code folders with this shared project.
- Added `v485_8mm` and `v485_12_16_24mm` environments. The source comparison found the meaningful functional difference: the wider variant keeps the PA8/PA12 peel motor running from startup and between feeds; 8 mm stops both motors at the pulse count. Environment selection preserves that behaviour without duplicate applications.
- Split plain C sources into `main.c`, board support, feeder application, RS485, EEPROM and display modules with matching headers. All application files, including `config.h`, live in `src/`. Mutable application/UART state is private to its owning module.
- Replaced legacy STM32F10x SPL GPIO, clock, UART and interrupt setup with HAL. Pinned official ST STM32 platform 20.0.0, STM32CubeF1 1.8.7 and GCC 14.2.1 (package 1.140201.0).
- Added explicit 8 MHz HSE / 72 MHz PLL setup, HAL millisecond timing and Cortex-M3 cycle-counter microsecond delays. PlatformIO supplies startup, framework and linker support.
- Preloaded stopped motor levels before enabling GPIO outputs, then applied the selected variant's startup levels. HAL/clock/UART setup failures force both motors high/stopped and light the LED.
- Retained I/O assignments, 9600-baud command protocol, EEPROM layout/defaults, CH455 display and feed/button logic. Cleared UART receive/error flags with the required F1 SR/DR sequence and ignored errored bytes. Removed the unused pending-flash branch, whose counter was never set in either source.
- Added a local version string and build variant to the startup address message. Clarified comments around acceptance replies, parser grammar and the blocking blanking delay.
- Added commented build configuration, environment selection instructions and navigation links. No tests folder or copied framework tree was added. No hardware upload, commit or push was performed.

### Validation

Both environments built successfully with the pinned packages:

| Environment | Flash / 65,536 bytes | Static RAM / 20,480 bytes |
| --- | --- | --- |
| `v485_8mm` | 11,672 bytes | 640 bytes |
| `v485_12_16_24mm` | 11,676 bytes | 640 bytes |

RAM figures exclude runtime stack/heap use. Verified the flash/vector base, initial stack pointer, application interrupt vectors and version/variant strings in both images. Temporary host checks with address/undefined-behaviour sanitizers passed startup/idle levels, addressed and busy replies, explicit/default feed counts, external triggers, pulse stopping and manual-trigger countdown for both variants. These checks used simulated hardware. The framework/linker warnings present in this initial build are resolved in 0.1.1; physical operation remains unverified.

### Original sources

Both original files are retained in this repository's initial Git revision; active application sources are now in `src/`.

| Imported source | Vendor identification | Original SHA-256 |
| --- | --- | --- |
| `V485_feeder_8mm.c` | Banner 8 mm V26; Version line V25 | `701c5520c1e80cf2becc244e8f141f8ddb13eaa4589eea2d2843b60acacd016c` |
| `V485_feeder_12-16-24mm.c` | V26 | `ea91d10dae360ab89fbda77119278508f6ac475cafa857af218f58722153b55e` |

Local semantic versioning starts at 0.1.0 and does not represent an upstream MicroSMT release. The separate V3 feeder programs have not been converted.
