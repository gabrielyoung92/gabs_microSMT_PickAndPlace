# V485 addressed RS485 firmware updates

This is Gab's local bootloader extension to the [MicroSMT-derived application](README.md), prepared with ChatGPT assistance. It has been built and checked with simulated hardware; **no physical installation or upload has been performed**.

## Destination IDs and images

Every request and reply contains **one destination ID, 0–99**. CRC32 covers the ID and command/data together. A different ID or damaged packet produces no reply and no write. Firmware files contain the width variant, not the individual feeder ID: one 8 mm file serves all 8 mm feeders, and one wider file serves 12/16/24 mm feeders.

The feeder's EEPROM ID and default count survive application updates. IDs **must be unique on the connected bus**; identical IDs cannot be distinguished by this protocol. Blank EEPROM uses commissioning ID 0. Connect/commission blank feeders one at a time, then set their individual IDs using the application's existing buttons. Unreadable/invalid EEPROM IDs leave the loader waiting without accepting a destination.

There is no broadcast update command. An explicit batch list updates/verifies one ID, then proceeds to the next, stopping on the first failure. Use a separate batch for each width variant.

## Memory and startup

| Area | Address / size | Purpose |
| --- | --- | --- |
| Bootloader flash | 0x08000000–0x08001FFF / 8 KB | SWD-installed loader, never written by RS485 update commands |
| Application flash | 0x08002000–0x0800FFFF / 56 KB | Application vectors, identity tag, code and data |
| 24C02 byte 0 | 0x00 | Existing feeder ID |
| 24C02 byte 1 | 0x01 | Existing default feed count |
| Boot state | EEPROM 0x1F | 0xA5 valid, 0x5A update requested, 0x00 writing |
| Boot record | EEPROM 0x20–0x33 | Format magic, width variant, size, image CRC32, record CRC32 |

Normal power-on checks EEPROM metadata, image identity, initial stack/reset vectors and the whole-image CRC, then enters the application. There is **no deliberate listening window**. These checks take time; physical boot time has not been measured. The application's existing startup flashes still run afterwards.

An addressed BOOT request is accepted only when no feed is reserved/running. It inhibits triggers, stops both motors, verifies the EEPROM request flag, acknowledges, then resets. Both motors remain stopped throughout loader operation, including the wider variant. Download mode waits indefinitely; an incomplete image never runs automatically.

Before flash erasure, the loader verifies an invalid/writing marker in EEPROM. DATA writes stay inside the declared application range, check packet CRCs and verify flash readback. END checks the full image, stores checked metadata, then writes the valid marker **last**. Flash failure or interrupted transfer leaves recovery mode available; rerun the upload. A reset loses transfer progress, so it restarts from the beginning.

This is one application slot, without A/B rollback. After erasure, the previous application cannot be restored automatically. CRC detects accidental corruption; it is not firmware authentication. The code sets no flash option-byte write protection; ST-Link can still recover or replace the loader.

## Build and initial installation

Open **CODE_feeder** in VS Code/PlatformIO. Build all images without hardware:

```sh
pio run -e v485_8mm -e v485_12_16_24mm -e bootloader_8mm -e bootloader_12_16_24mm
```

Select the matching width. Application files are `.pio/build/v485_8mm/firmware.bin` or `.pio/build/v485_12_16_24mm/firmware.bin`; loader files are in the corresponding `bootloader_*` directories. They are different binaries and are not interchangeable.

For the eventual **first hardware installation**, after confirming chip/crystal/wiring and stopping the machine:

1. Connect ST-Link/SWD and install only the matching loader, for example `pio run -e bootloader_8mm -t upload`. This replaces the old firmware at flash base. It does not initialise EEPROM boot metadata; absent/invalid metadata leads to recovery mode.
2. Connect a suitable **auto-direction USB-RS485 adapter** to the feeder bus. Keep the ordinary controller and other serial masters disconnected from bus traffic during uploading. Close serial monitors. The current ESP32 controller does not forward these update packets, so use the adapter directly.
3. Send the matching application to its existing EEPROM ID using the uploader below. If EEPROM is blank, connect only that commissioning feeder and select ID 0. The first successful upload creates the boot record and starts the application.

Installing an application with ST-Link alone does not create the EEPROM record required for boot. For normal updates, use the RS485 path. Bootloader replacement itself always remains an SWD operation.

## Upload from Windows / PlatformIO

From a PlatformIO terminal in this directory, using Python with pyserial (PlatformIO's bundled Python already includes it):

```sh
# Offline: inspect the file without opening a port.
python tools/rs485_upload.py --firmware .pio/build/v485_8mm/firmware.bin --inspect

# One destination. Substitute the adapter port and the feeder's actual ID.
python tools/rs485_upload.py --port COM5 --address 7 --firmware .pio/build/v485_8mm/firmware.bin

# Explicit destinations, updated one at a time; no broadcast.
python tools/rs485_upload.py --port COM5 --addresses 7,8,9 --firmware .pio/build/v485_8mm/firmware.bin
```

If plain `python` cannot import `serial`, use PlatformIO's Python or install `pyserial` into that Python. The link is 9600 baud, 8N1, LF. Uploads use 32-byte stop-and-wait chunks and report progress. A running application is queried for its width before BOOT; an active feed returns an error rather than being interrupted. A loader rejects the wrong width/base/size before erasing anything.

For VS Code's **PlatformIO Upload** button, set `custom_feeder_address` in the application's selected environment in [platformio.ini](platformio.ini), replacing `REQUIRED` with the actual ID. Select the adapter's upload port, or use:

```sh
pio run -e v485_8mm -t upload --upload-port COM5
```

The default `REQUIRED` value deliberately fails validation before opening the port. Bootloader environments use ST-Link upload instead. Build tasks never upload.

## Shared source and wire format

`board.c`, `rs485.c`, `display.c`, `eeprom.c` and `boot.c` are compiled into both images; there are no copied drivers. Source filters select `main.c`/`feeder.c` for applications or `bootloader.c` for loaders. Boot builds disable the wider idle motor behaviour and use link-time optimisation to fit the 8 KB region. Application `SystemInit` and the linker agree on the 0x2000 vector offset.

Protocol version 1 uses ASCII, with ID as exactly two decimal digits. Numbers below are exactly eight hexadecimal digits. Every line is:

```text
B07 <command and fields> <CRC32> LF
```

CRC32 is the IEEE/zlib value over ASCII from `B` through the last command/data character, excluding the space before the checksum and LF. Replies have the same prefix/checksum rule. Examples here show bodies only; the uploader supplies destination/checksum automatically.

| Request body | Reply body | Meaning |
| --- | --- | --- |
| `INFO` | `APP <variant> <size> <imageCRC>` | Running application's committed metadata |
| `BOOT` | `RESET` | Running app records request and resets; busy/write failure returns ERROR |
| `HELLO` | `READY <variant> <appBase> <maxSize>` | Loader identity/layout |
| `BEGIN <variant> <size> <imageCRC>` | `OK <nextOffset>` | Invalidate metadata and erase application pages; identical live-session retry preserves progress |
| `DATA <offset> <hexBytes>` | `OK <nextOffset>` | Write/read back up to 32 bytes; matching duplicate data is acknowledged without programming again |
| `END <imageCRC>` | `DONE <imageCRC>` | Verify whole image/vectors/tag, commit EEPROM and enter app |

Variant 1 is 8 mm; variant 2 is 12/16/24 mm. Application offset 0x200 contains `V485APP\0`, a little-endian variant word and application-base word. The boot record uses little-endian 32-bit words; its magic is 0x31423556, followed by variant/size/image CRC and CRC of those first 16 bytes. No EEPROM write happens for individual DATA chunks or normal boots.

A lost final DONE is checked by querying the running application's INFO after startup. A reported verification/EEPROM/flash failure stops the uploader. Legacy `N<id> F<count>` feeds retain their existing protocol and do **not** acquire firmware-upload retry semantics.

## Software verification

All four pinned environments build without compiler/linker warnings. Temporary actual-C checks with address/undefined-behaviour sanitizers cover wrong/corrupted destination IDs, malformed packets, EEPROM failure at each metadata write, flash range limits, duplicate BEGIN/DATA, interrupted-transfer restart, odd final bytes, width/vector/tag/CRC rejection and preserved ID/count bytes. Existing feeder/ISR regression checks and application BOOT busy/fault/EEPROM-failure paths pass for both variants. The actual C loader and Python uploader were also connected through a simulated serial adapter, including lost acknowledgements and stale ACKs.

Run the retained small offline check without hardware or a tests folder:

```sh
python tools/rs485_upload.py --self-check
```

These checks do not prove physical RS485 turnaround, motor stopping, EEPROM behaviour under real brownouts or SWD installation. No hardware was flashed.

Implementation references: [ST flash programming manual PM0075](https://www.st.com/resource/en/programming_manual/pm0075-stm32f10xxx-flash-memory-microcontrollers-stmicroelectronics.pdf), [PlatformIO custom upload commands](https://docs.platformio.org/en/latest/projectconf/sections/env/options/upload/upload_command.html).
