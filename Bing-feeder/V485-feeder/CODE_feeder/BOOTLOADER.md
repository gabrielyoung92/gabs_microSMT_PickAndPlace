# V485 RS485 firmware updates

Local bootloader extension to the [MicroSMT-derived feeder firmware](README.md). **Software checks pass; physical installation and operation remain untested.** [Validation results](CHANGELOG.md#software-checks).

## Destination IDs

Every update request/reply includes a **transport destination, 0–99**, protected by CRC32 along with the payload. Other IDs ignore the packet. One firmware file serves every feeder of the matching width; the feeder's saved ID/count survive updates.

IDs must be **unique on the connected bus**. Operating IDs are **1–99**. Blank ID byte `FF` is saved as `0`: this is unassigned, flashes **00**, and blocks both motors and all advances. Address 0 is reserved for programming/recovery only. Commission unassigned feeders one at a time, then set individual IDs with PA2 menu `03` or the [locally armed ID assignment tool](README.md#set-an-id-from-the-pc). Unreadable/invalid EEPROM IDs leave the loader waiting.

Batch uploads update and verify one ID at a time, stopping on the first failure. Use a separate batch for each width. There is no broadcast update command.

## First installation

For the current batch, use the [ST-Link-only commissioning tool](COMMISSIONING.md),
which programs both images and verified EEPROM metadata/settings without RS485.
The separate loader/RS485 procedure below remains available.


Open **CODE_feeder** in VS Code/PlatformIO and build the matching application and loader:

```sh
pio run -e v485 -e bootloader
```

After confirming the chip, crystal and wiring, stop the machine and:

1. Install the matching loader over ST-Link/SWD, for example `pio run -e bootloader -t upload`. This replaces the old firmware at flash base. Missing/invalid EEPROM metadata leaves it in recovery mode.
2. Connect the [ESP32-C3 controller running the local 0.1.0 development firmware with the update bridge](../../V485-Feeder%20Controller/CODE_esp32C3/README.md) to the feeder bus and PC USB. An auto-direction USB-RS485 adapter connected directly to the bus is also supported. Close OpenPnP/serial monitors and stop other bus masters; use only one RS485 master.
3. Upload the matching application to its existing ID using the command below. The first upload creates the boot record and starts the application. For blank EEPROM, connect only that commissioning feeder and select ID 0.

The common application is `.pio/build/v485/firmware.bin`; the common loader is `.pio/build/bootloader/firmware.bin`. Width is an EEPROM setting. Installing an application with ST-Link alone does not create its EEPROM boot record. Loader replacement remains an SWD operation.

## Upload from Windows

Run from this directory using Python with pyserial. PlatformIO's Python includes it; for another Python installation, install `pyserial` there.

```sh
# Inspect without opening a serial port.
python tools/rs485_upload.py --firmware .pio/build/v485/firmware.bin --inspect

# Replace COM5 and 7 with the controller/adapter USB port and actual feeder ID.
python tools/rs485_upload.py --port COM5 --address 7 --firmware .pio/build/v485/firmware.bin

# Update explicit IDs sequentially.
python tools/rs485_upload.py --port COM5 --addresses 7,8,9 --firmware .pio/build/v485/firmware.bin
```

The RS485 link is **115200 baud, 8N1, LF** for both application and bootloader. Use matching 115200 builds on every connected node; an older 9600-baud loader needs replacement over SWD before it can use these tools. The uploader works unchanged through the ESP32-C3 controller or a direct adapter. Native controller USB is independent of the uploader's 115200-baud host setting. The uploader retries initial HELLO discovery before checking for a running application, checks the universal image format and memory layout, requests download mode and verifies the upload. An active feed rejects the request. Old width-specific or foreign images are rejected before erasure.

With the ESP32-C3 controller, feed commands remain blocked until update traffic has been idle for 10 seconds. Close the uploader and wait for that interval before reconnecting OpenPnP. The controller handles packet forwarding and bus direction only; the uploader retains update retries and verification.

For PlatformIO's **Upload** button, set `custom_feeder_address` in [platformio.ini](platformio.ini) to the actual ID instead of `REQUIRED`, then select the controller/adapter USB port:

```sh
pio run -e v485 -t upload --upload-port COM5
```

Application Upload uses RS485; loader Upload uses ST-Link. Build tasks only compile.

## Startup and recovery

Normal startup checks metadata, universal image identity, vectors and the whole-image CRC, then enters the application without a listening delay. The application still runs its startup flashes; physical boot time is unmeasured.

PA2 menu `02` or an addressed BOOT request stops both motors, saves the update request and resets. Both motors stay stopped in the loader, regardless of the configured width. Requested, missing or invalid firmware leaves it waiting indefinitely for an upload.

Before erasing flash, the loader verifies an invalid/writing EEPROM marker. It checks each data packet and flash readback, then verifies the complete image before writing the valid marker **last**. After an interrupted upload, rerun the command. A reset loses transfer progress and requires restarting from the beginning; lost acknowledgements within a live session can be retried.

This uses one application slot: **there is no A/B rollback** after erasure. CRC detects corruption, not malicious firmware. RS485 commands cannot write the loader region or flash option bytes; no option-byte write protection is configured.

## Memory layout

| Area | Location | Contents |
| --- | --- | --- |
| Bootloader | Flash 0x08000000–0x08001FFF / 8 KB | Installed over SWD |
| Application | Flash 0x08002000–0x0800FFFF / 56 KB | Vectors, identity, code and data |
| Feeder settings | EEPROM bytes 0 / 1 / 2 / 3 | ID / default event count / width / width complement (invalid pair = unconfigured) |
| Motor/switch options | EEPROM 0x04–0x06 | Flags / complement / A1 schema marker; see application README |
| Boot state | EEPROM 0x1F | 0xA5 valid, 0x5A requested, 0x00 writing |
| Boot record | EEPROM 0x20–0x33 | Magic, width, size, image CRC and record CRC |

## Protocol reference

<details>
<summary>Packet fields</summary>

All packets use `B07 <body> <CRC32>` followed by LF. The ID is exactly two decimal digits. CRC32 is IEEE/zlib over ASCII from `B` through the final body character, excluding the space before the checksum and LF. Replies use the same format; numeric fields are eight hexadecimal digits.

| Request body | Reply body | Purpose |
| --- | --- | --- |
| `INFO` | `APP <variant> <size> <imageCRC>` | Running application's committed metadata |
| `BOOT` | `RESET` | Record update request and reset; reject busy/write failure |
| `DIAG <nonce>` | `DIAG <nonce> <tokenHi> <tokenLo> <movementTotal> <flags>` | Application diagnostic snapshot, including during settings faults |
| `MONITOR <nonce> <tokenHi> <tokenLo>` | Same DIAG reply | Claim an empty RAM token; a nonzero token cannot be replaced until MCU reset; never resets counters or enables motion |
| `IDENT <nonce>` | `IDENT <nonce> <uid0> <uid1> <uid2> <armed>` | Application hardware identity and menu 01 selection; read-only, including during a settings fault |
| `TYPE <nonce>` | `TYPE <nonce> <width> <count> <stepUm>` | Read saved width/default count and nominal micrometres per optical event |
| `SETTYPE <nonce> <uid0> <uid1> <uid2> <width>` | `TYPESET <nonce> <width>` | Matching UID and idle feed required; direct bus setting, no menu; checked EEPROM save |
| `CONFIG <nonce>` | `CONFIG <nonce> <feedReverse> <peelReverse> <switchNO>` | 0.1.1 read-only settings; booleans 0/1 |
| `SETCONFIG <nonce> <uid0> <uid1> <uid2> <feedReverse> <peelReverse> <switchNO>` | `CONFIGSET <nonce> <feedReverse> <peelReverse> <switchNO>` | Matching UID; no menu; rejects active feeds, stops idle peeling; booleans 0/1, verified EEPROM write |
| `SETCOUNT <nonce> <uid0> <uid1> <uid2> <count>` | `COUNTSET <nonce> <count>` | Direct saved default count 1–99; matching UID, no menu; rejects active feeds |
| `JOG <token0> <token1> <retract> <items>` | `ACCEPT/BUSY/FAULT <token0> <token1>` | Retract 0/1, positive items; items × saved default events ≤10000; 32-bit progress, 3 s stall guard and scaled total deadline; peel inhibited until next regular feed/reset; STATUS reports completion |
| `STOP <nonce>` | `STOPPED <nonce>` | Immediately disables both motors, latches E4 and faults any active request; reset required |
| `LOCATE <nonce>` | `LOCATING <nonce>` or `BUSY <nonce>` | Flash display/LED for about four seconds with motors stopped |
| `SETID <nonce> <uid0> <uid1> <uid2> <newID>` | `ID <nonce> <newID>` at the old ID | Application only: require menu 01, matching hardware UID and new ID 1–99; save/read back before changing ID |
| `HELLO` | `READY <variant> <appBase> <maxSize>` | Loader identity/layout |
| `BEGIN <variant> <size> <imageCRC>` | `OK <nextOffset>` | Invalidate metadata and erase; identical live-session retry keeps progress |
| `DATA <offset> <hexBytes>` | `OK <nextOffset>` | Write/read back up to 32 bytes; acknowledge matching duplicates without rewriting |
| `END <imageCRC>` | `DONE <imageCRC>` | Verify, commit and start application |

Application diagnostic fields use the same eight-digit hexadecimal encoding. Movement total increments on every serviced PA3 rising edge, modulo 2^32. The host first reads DIAG, then claims a zero token with a random nonzero pair. The token and total survive PC restarts while the MCU stays powered; both clear on MCU reset. No EEPROM is written for telemetry. A monitor token is correlation data, not authentication or a motion permission.

Diagnostic flags: bits 0–7 saved default count; 8–15 fault (0 none, 1 index deadline, 2 peel deadline, 3 settings failure); 16–19 feed state (0 idle, 1 reserved, 2 running, 3 fault); 20–23 UI mode (0 normal, 1 menu, 2 remote ID, 3 local ID, 4 count, 5 type); bit 24 raw switch contact permits peel; bit 25 peel output commanded running; bit 26 application ready; bit 27 assigned ID; bit 28 wider configured type; bit 29 valid configured type; bits 30–31 type index (0=8, 1=12, 2=16, 3=24; meaningful only if bit 29 is set). The shutdown used for a requested update can have feed state fault with fault code 0; it is not a recorded motor fault.

The assignment tool probes for an occupied destination before SETID, then verifies the hardware UID at the new ID. SETID does not perform its own bus probe. Assignment consumes the local selection; it cannot be retried after success without selecting menu 01 again. ID and nonce fields use the same eight-digit hexadecimal encoding as other numeric fields.

Image format 3 is universal; old format 1/2 images are rejected. Physical width is stored separately in EEPROM byte 2, with its complement at byte 3; configuration invalidates byte 2 before writing and commits the width last. At application offset 0x200, the image tag contains `V485APP\0`, then little-endian variant and base-address words. The EEPROM record contains five little-endian words: magic 0x31423556, variant, size, image CRC and CRC of the first 16 bytes.

The uploader confirms a lost DONE through the running application's INFO. Update retries do not apply to legacy feed commands. Shared driver and metadata code is in [src/](src/).

</details>

Run the small offline check with `python tools/rs485_upload.py --self-check`. See the [changelog](CHANGELOG.md#software-checks) for build sizes and detailed checks.
