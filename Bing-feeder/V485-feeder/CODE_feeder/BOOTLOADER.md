# V485 RS485 firmware updates

Local bootloader extension to the [MicroSMT-derived feeder firmware](README.md). **Software checks pass; physical installation and operation remain untested.** [Validation results](CHANGELOG.md#software-checks).

## Destination IDs

Every update request/reply includes a **transport destination, 0–99**, protected by CRC32 along with the payload. Other IDs ignore the packet. One firmware file serves every feeder of the matching width; the feeder's saved ID/count survive updates.

IDs must be **unique on the connected bus**. Operating IDs are **1–99**. Blank ID byte `FF` is saved as `0`: this is unassigned, flashes **00**, and blocks both motors and all advances. Address 0 is reserved for programming/recovery only. Commission unassigned feeders one at a time, then set individual IDs with PA4 menu `03` or the [locally armed ID assignment tool](README.md#set-an-id-from-the-pc). Unreadable/invalid EEPROM IDs leave the loader waiting.

Batch uploads update and verify one ID at a time, stopping on the first failure. Use a separate batch for each width. There is no broadcast update command.

## First installation

Open **CODE_feeder** in VS Code/PlatformIO and build the matching application and loader:

```sh
# 8 mm
pio run -e v485_8mm -e bootloader_8mm
# 12 / 16 / 24 mm
pio run -e v485_12_16_24mm -e bootloader_12_16_24mm
```

After confirming the chip, crystal and wiring, stop the machine and:

1. Install the matching loader over ST-Link/SWD, for example `pio run -e bootloader_8mm -t upload`. This replaces the old firmware at flash base. Missing/invalid EEPROM metadata leaves it in recovery mode.
2. Connect the [ESP32-C3 controller running the local 0.1.0 development firmware with the update bridge](../../V485-Feeder%20Controller/CODE_esp32C3/README.md) to the feeder bus and PC USB. An auto-direction USB-RS485 adapter connected directly to the bus is also supported. Close OpenPnP/serial monitors and stop other bus masters; use only one RS485 master.
3. Upload the matching application to its existing ID using the command below. The first upload creates the boot record and starts the application. For blank EEPROM, connect only that commissioning feeder and select ID 0.

Application binaries are `.pio/build/v485_8mm/firmware.bin` and `.pio/build/v485_12_16_24mm/firmware.bin`. Loader binaries are in the corresponding `bootloader_*` folders. Installing an application with ST-Link alone does not create its EEPROM boot record. Loader replacement remains an SWD operation.

## Upload from Windows

Run from this directory using Python with pyserial. PlatformIO's Python includes it; for another Python installation, install `pyserial` there.

```sh
# Inspect without opening a serial port.
python tools/rs485_upload.py --firmware .pio/build/v485_8mm/firmware.bin --inspect

# Replace COM5 and 7 with the controller/adapter USB port and actual feeder ID.
python tools/rs485_upload.py --port COM5 --address 7 --firmware .pio/build/v485_8mm/firmware.bin

# Update explicit IDs sequentially.
python tools/rs485_upload.py --port COM5 --addresses 7,8,9 --firmware .pio/build/v485_8mm/firmware.bin
```

The RS485 link is **9600 baud, 8N1, LF**. The uploader works unchanged through the ESP32-C3 controller or a direct adapter. Native controller USB is independent of the uploader's 9600-baud host setting. The uploader retries initial HELLO discovery before checking for a running application, checks the image's width and memory layout, requests download mode and verifies the upload. An active feed rejects the request. Wrong-width images are rejected before erasure.

With the ESP32-C3 controller, feed commands remain blocked until update traffic has been idle for 10 seconds. Close the uploader and wait for that interval before reconnecting OpenPnP. The controller handles packet forwarding and bus direction only; the uploader retains update retries and verification.

For PlatformIO's **Upload** button, set `custom_feeder_address` in [platformio.ini](platformio.ini) to the actual ID instead of `REQUIRED`, then select the controller/adapter USB port:

```sh
pio run -e v485_8mm -t upload --upload-port COM5
```

Application Upload uses RS485; loader Upload uses ST-Link. Build tasks only compile.

## Startup and recovery

Normal startup checks metadata, image identity, vectors and the whole-image CRC, then enters the application without a listening delay. The application still runs its startup flashes; physical boot time is unmeasured.

PA4 menu `02` or an addressed BOOT request stops both motors, saves the update request and resets. Both motors stay stopped in the loader, including the wider variant. Requested, missing or invalid firmware leaves it waiting indefinitely for an upload.

Before erasing flash, the loader verifies an invalid/writing EEPROM marker. It checks each data packet and flash readback, then verifies the complete image before writing the valid marker **last**. After an interrupted upload, rerun the command. A reset loses transfer progress and requires restarting from the beginning; lost acknowledgements within a live session can be retried.

This uses one application slot: **there is no A/B rollback** after erasure. CRC detects corruption, not malicious firmware. RS485 commands cannot write the loader region or flash option bytes; no option-byte write protection is configured.

## Memory layout

| Area | Location | Contents |
| --- | --- | --- |
| Bootloader | Flash 0x08000000–0x08001FFF / 8 KB | Installed over SWD |
| Application | Flash 0x08002000–0x0800FFFF / 56 KB | Vectors, identity, code and data |
| Feeder settings | EEPROM bytes 0 / 1 | ID / default count |
| Boot state | EEPROM 0x1F | 0xA5 valid, 0x5A requested, 0x00 writing |
| Boot record | EEPROM 0x20–0x33 | Magic, width, size, image CRC and record CRC |

<details>
<summary>Protocol reference</summary>

All packets use `B07 <body> <CRC32>` followed by LF. The ID is exactly two decimal digits. CRC32 is IEEE/zlib over ASCII from `B` through the final body character, excluding the space before the checksum and LF. Replies use the same format; numeric fields are eight hexadecimal digits.

| Request body | Reply body | Purpose |
| --- | --- | --- |
| `INFO` | `APP <variant> <size> <imageCRC>` | Running application's committed metadata |
| `BOOT` | `RESET` | Record update request and reset; reject busy/write failure |
| `IDENT <nonce>` | `IDENT <nonce> <uid0> <uid1> <uid2> <armed>` | Application hardware identity and menu 01 selection; read-only, including during a settings fault |
| `SETID <nonce> <uid0> <uid1> <uid2> <newID>` | `ID <nonce> <newID>` at the old ID | Application only: require menu 01, matching hardware UID and new ID 1–99; save/read back before changing ID |
| `HELLO` | `READY <variant> <appBase> <maxSize>` | Loader identity/layout |
| `BEGIN <variant> <size> <imageCRC>` | `OK <nextOffset>` | Invalidate metadata and erase; identical live-session retry keeps progress |
| `DATA <offset> <hexBytes>` | `OK <nextOffset>` | Write/read back up to 32 bytes; acknowledge matching duplicates without rewriting |
| `END <imageCRC>` | `DONE <imageCRC>` | Verify, commit and start application |

The assignment tool probes for an occupied destination before SETID, then verifies the hardware UID at the new ID. SETID does not perform its own bus probe. Assignment consumes the local selection; it cannot be retried after success without selecting menu 01 again. ID and nonce fields use the same eight-digit hexadecimal encoding as other numeric fields.

Variant 1 is 8 mm; variant 2 is 12/16/24 mm. At application offset 0x200, the image tag contains `V485APP\0`, then little-endian variant and base-address words. The EEPROM record contains five little-endian words: magic 0x31423556, variant, size, image CRC and CRC of the first 16 bytes.

The uploader confirms a lost DONE through the running application's INFO. Update retries do not apply to legacy feed commands. Shared driver and metadata code is in [src/](src/).

</details>

Run the small offline check with `python tools/rs485_upload.py --self-check`. See the [changelog](CHANGELOG.md#software-checks) for build sizes and detailed checks.
