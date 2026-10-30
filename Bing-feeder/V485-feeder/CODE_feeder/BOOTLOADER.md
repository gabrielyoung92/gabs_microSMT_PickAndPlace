# V485 RS485 firmware updates

The installed bootloader updates the [current universal feeder application](README.md)
over addressed RS485. Normal updates use the dashboard and leave the loader alone.
Application transfers and CRC verification have been checked on bench units.

## Destination IDs

Every update request/reply includes a **transport destination, 0–99**, protected by CRC32 along with the payload. Other IDs ignore the packet. One universal firmware file serves all four feeder widths; the feeder's saved ID/count survive updates.

IDs must be **unique on the connected bus**. Operating IDs are **1–99**. Blank ID byte `FF` is saved as `0`: this is unassigned, flashes **00**, and blocks both motors and all advances. Address 0 is reserved for programming/recovery only. Commission unassigned feeders one at a time, then set individual IDs with PA2 menu `03` or the [locally armed ID assignment tool](README.md#direct-serial-tools). Unreadable/invalid EEPROM IDs leave the loader waiting.

Updates target and verify one ID at a time; there is no broadcast erase/write.
The dashboard queue continues with other units after a failure and supports an
explicit retry. The standalone uploader batch stops on its first failure.

## First installation

Use [ST-Link commissioning](COMMISSIONING.md) for a new or SWD-repaired board.
That procedure installs the loader/application and verifies the EEPROM boot
record, ID and width. Normal application updates leave the loader alone.

```sh
pio run -e v485 -e bootloader
```

Application: `.pio/build/v485/firmware.bin`. Loader:
`.pio/build/bootloader/firmware.bin`. An application-only SWD write does not
create its EEPROM boot record.

## Direct serial update

Run from this directory using Python with pyserial. PlatformIO's Python includes it; for another Python installation, install `pyserial` there.

```sh
# Inspect without opening a serial port.
python tools/rs485_upload.py --firmware .pio/build/v485/firmware.bin --inspect

# Replace COM5 and 7 with the controller/adapter USB port and actual feeder ID.
python tools/rs485_upload.py --port COM5 --address 7 --firmware .pio/build/v485/firmware.bin

# Update explicit IDs sequentially.
python tools/rs485_upload.py --port COM5 --addresses 7,8,9 --firmware .pio/build/v485/firmware.bin
```

The RS485 link is **115200 baud, 8N1, LF** for both application and bootloader. The uploader works unchanged through the ESP32-C3 controller or a direct adapter. Native controller USB is independent of the uploader's 115200-baud host setting. The uploader retries initial HELLO discovery before checking for a running application, checks the universal image format and memory layout, requests download mode and verifies the upload. An active feed rejects the request. Images with an incompatible format/layout are rejected before erasure.

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

This uses one application slot: **there is no A/B rollback** after erasure. RS485 writes are limited to the application region; flash option bytes and
the loader are not writable through this protocol.

## Memory layout

| Area | Location | Contents |
| --- | --- | --- |
| Bootloader | Flash 0x08000000–0x08001FFF / 8 KB | Installed over SWD |
| Application | Flash 0x08002000–0x0800FFFF / 56 KB | Vectors, identity, code and data |
| Feeder settings | EEPROM bytes 0 / 1 / 2 / 3 | ID / default event count / width / width complement (invalid pair = unconfigured) |
| Motor/switch options | EEPROM 0x04–0x06 | Flags / complement / A1 schema marker; see application README |
| Stock | EEPROM 0x40–0xFF | Application 0.1.4: twelve rotating quantity/advance records; loader leaves them untouched |
| Boot state | EEPROM 0x1F | 0xA5 valid, 0x5A requested, 0x00 writing |
| Boot record | EEPROM 0x20–0x33 | Magic, width, size, image CRC and record CRC |

## Protocol reference

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
| `CONFIG <nonce>` | `CONFIG <nonce> <feedReverse> <peelReverse> <switchNO>` | Read-only settings; booleans 0/1 |
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

DIAG flag layout:

| Bits | Meaning |
| --- | --- |
| 0–7 | Saved default event count |
| 8–15 | Fault: 0 none, 1 index timeout, 2 peel timeout, 3 settings, 4 STOP |
| 16–19 | Feed state: 0 idle, 1 reserved, 2 running, 3 fault |
| 20–23 | Mode: 0 normal, 1 menu, 2 remote ID, 3 local ID, 4 count, 5 type, 6 test |
| 24 | Interpreted peel request |
| 25 | Peel output running |
| 26 | Application ready |
| 27 | ID assigned |
| 28 | Wider feeder type |
| 29 | Valid configured type |
| 30–31 | Width index: 0=8, 1=12, 2=16, 3=24; valid when bit 29 is set |

A requested update can report feed state fault with fault code 0 during shutdown.

The assignment tool probes for an occupied destination before SETID, then verifies the hardware UID at the new ID. SETID does not perform its own bus probe. Assignment consumes the local selection; it cannot be retried after success without selecting menu 01 again. ID and nonce fields use the same eight-digit hexadecimal encoding as other numeric fields.

Image format 3 is universal. Physical width is stored separately in EEPROM byte 2, with its complement at byte 3; configuration invalidates byte 2 before writing and commits the width last. At application offset 0x200, the image tag contains `V485APP\0`, then little-endian variant and base-address words. The EEPROM record contains five little-endian words: magic 0x31423556, variant, size, image CRC and CRC of the first 16 bytes.

The uploader confirms a lost DONE through the running application's INFO. Update retries never authorize a repeated feeder advance. Shared driver and metadata code is in [src/](src/).


Run the small offline check with `python tools/rs485_upload.py --self-check`. See the [firmware notes](CHANGELOG.md#verification) for verification status.

### Application 0.1.2 input test (no loader update needed)

`TESTREAD nonce` replies `TEST nonce flags switchChanges uptimeMs movementTotal`
(five 32-bit hexadecimal fields, standard addressed CRC packet). Flags: bit0
motor-off test active, bit1 PB6 contact closed/LOW, bit2 interpreted peel request
(NC/NO applied), bit3 peel motor running, bit4 index motor running, bit5 PA4 feed
button pressed, bit6 PA2 menu button pressed, bit7 PA3 optical input HIGH.
`switchChanges` counts transitions stable for at least 20 ms during the test;
`uptimeMs` wraps as a 32-bit millisecond counter. `movementTotal` retains normal
stock-counter semantics, including hand movement; it is not reset by testing.

`TEST nonce uid0 uid1 uid2 enabled` sets test mode (`enabled` 00000001) or exits
(00000000). Rejects wrong UID/invalid boolean without action; active movement or
menus reply `BUSY nonce`. Accepted commands reply with the same `TEST` snapshot.
Repeated Start preserves counters. No EEPROM writes, unsolicited events, feed
requests, fault clear or automatic timeout/resumption. Exit re-enables normal
operation only when fault-free; all widths may then take up tape if already armed by an ordinary feed. Reset exits
RAM-only test mode through the usual startup. The host reads TESTREAD before
attempting Start.

### Clear runtime faults

The application accepts `CLEAR nonce uid0 uid1 uid2` in a standard addressed
CRC packet. All four fields are hexadecimal words. Matching UID replies
`CLEARED nonce`; active movement or a menu replies `BUSY nonce`; invalid saved
settings reply `ERROR SETTINGS nonce`. Wrong UID or malformed requests do
nothing. Clear resets E1/E2/E4 without a reboot or EEPROM writes. Both motors
remain stopped until the next ordinary feed or restart. Test mode stays active,
and the interrupted request still reports its original fault.

### Application startup notification

The application sends one `ONLINE uid0 uid1 uid2`
packet, using the same `Bdd ... CRC32` framing and three eight-digit hexadecimal
UID words. It waits `ID × 12 + (uid0 & 7)` milliseconds before transmission.
This reduces simultaneous-start collisions; it does not arbitrate a busy bus.
No acknowledgement or retry is expected. The host schedules a normal status
check for configured polling IDs; missed hellos fall back to polling. This is
separate from the existing bootloader's host-requested `HELLO` command.

## Saved stock commands

Application 0.1.4 accepts these addressed commands. Values are eight-digit
hexadecimal words; wrong-UID writes are ignored.

| Command | Reply | Behaviour |
| --- | --- | --- |
| `STOCKREAD nonce` | `STOCK nonce remaining advances sequence` | Reads RAM snapshot; never writes EEPROM |
| `SETSTOCK nonce uid0 uid1 uid2 quantity` | `STOCK nonce remaining advances sequence` | Quantity 0–65,534; saves and resets advances to zero |

Remaining `0000FFFF` means Not set. Advances saturate at `FFFFFFFF`.
SETSTOCK rejects active/reserved feeds and local menus/tests with BUSY. Invalid
quantity reports ERROR QUANTITY; failed EEPROM access reports ERROR EEPROM/E3.
A lost SET reply is checked by STOCKREAD, not an automatic repeat of SETSTOCK.

## Bench commands in application 0.1.4

| Command | Reply | Meaning |
| --- | --- | --- |
| `FAULTINFO nonce` | `FAULTINFO nonce flags target received duration` | Last fault snapshot; duration in milliseconds |
| `HEALTH nonce` | `HEALTH nonce resetFlags uptime` | Captured RCC CSR reset flags and uptime in milliseconds |
| `LOAD nonce uid0 uid1 uid2 action` | `LOAD nonce active peelRequested` | Explicit loading controls; wrong UID ignored |

FAULTINFO flags: low byte = E1/E2/E3/E4 reason; bit 8 = switch contact closed;
bit 9 = NO polarity; bit 10 = peel was running. Target/received are sensor events
for an active index move, otherwise zero. Duration is peel time for E2, active
index time for other movement faults, otherwise zero. Snapshot stays until clear
or reset. No EEPROM writes are involved.

HEALTH uses the STM32 RCC CSR bits: 26 reset pin, 27 power-on, 28 software,
29 independent watchdog, 30 window watchdog, 31 low-power. Multiple flags can be
set. The installed loader's HAL_RCC_DeInit clears them, so zero means **cause
unavailable**, not a particular reset cause. The loader remains unchanged.

LOAD actions: `0` end, `1` enter, `2` peel to tension, `3` stop. Values are
hexadecimal words as elsewhere. Busy replies retain the nonce. Loading is mode
`7` in DIAG; normal FEED and local button feeding are inhibited. JOG remains
available for index feed/retract and does not change stock. Enter may stop idle
peeling. End rejects active movement; stop first. Peel-only stops on the switch
or the existing E2 timeout; browser loss cannot extend it. Clearing a fault
holds peel stopped. No command automatically retries a loading movement.
