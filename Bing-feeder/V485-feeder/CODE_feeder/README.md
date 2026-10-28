# V485 feeder firmware — 8/12/16/24 mm

> Designs and original files by [MicroSMT](https://github.com/microsmt/Bing-feeder). [Credits and local changes](../../../CREDITS.md).

One universal STM32 HAL/PlatformIO application and bootloader serve every width.
Version 0.1.1 adds per-unit EEPROM motor directions and peel-switch polarity.
0.1.0 communication and an unloaded feed motor have been checked on one 8 mm
board. The 0.1.1 RS485 update and direct settings save/readback have been verified on
one board without menu selection; motor behaviour with the new settings is pending.

## Per-unit motor and switch settings (0.1.1)

All widths use the same application. EEPROM stores independent **feed direction**,
**peel direction**, and **peel switch polarity**. The **8 mm defaults** are
**reversed feed / normal peel / NC**, with **two events per item (4 mm)**. Wider
units default to normal feed / normal peel / NC and one event per item (4 mm).
Normal retains 0.1.0 output polarity; reversed exchanges the two drive inputs.
Direction settings preserve stop/brake outputs and optical counting. Item-move
watchdogs are described below; ordinary feed and peel deadlines remain 10 seconds.

| Switch setting | Contact to GND permits peeling | Contact to GND stops peeling |
| --- | --- | --- |
| NC (default) | Closed / PB6 LOW | Open / PB6 HIGH |
| NO | Open / PB6 HIGH | Closed / PB6 LOW |

These describe electrical behaviour, assuming tension actuates the mounted switch.
In NO mode a disconnected switch also requests peeling. On 8 mm units peeling
still requires an active feed; on wider units it can run while the feeder is idle.
The opto's PA3 rising-edge counting is unchanged.

Use the direct automatic-direction adapter at 115200 8N1. Stop the USB host or
other port owners first. Read settings without moving motors:

```sh
python tools/configure_unit.py --port YOUR_PORT --address 9
```

Change settings directly over RS485, with no button/menu selection (all three choices are explicit):

```sh
# Reverse this unit's feed motor; retain normal peel direction and NC switch.
python tools/configure_unit.py --port YOUR_PORT --address 9 --feed reversed --peel normal --switch nc
```

The command checks the hardware UID, sends the save once, and verifies readback.
A lost save acknowledgement triggers reads, never a repeated save. The addressed, CRC-checked command stops idle peeling during the write and
activates the verified settings immediately. An active feed rejects changes with BUSY.
Menu 01 is required only for bus ID reassignment. Settings survive power cycles and subsequent application uploads.
The separate testing application is not part of this update.

EEPROM bytes **0x04/0x05/0x06** contain flags / complement / schema marker **A1**.
Flags bits 0/1/2 mean feed reversed / peel reversed / NO. All FF means an untouched
0.1.0 extension and uses the width-specific direction default without boot-time
option writes. A missing/invalid default count is saved as 2 for a configured
8 mm unit, otherwise 1. Valid saved options/counts remain authoritative; updating
an existing unit does not silently overwrite a custom profile. Commissioning tools
explicitly install the width-specific defaults. Other invalid records
inhibit both motors with **E3**, while serial queries and direct bus configuration
remain available. Re-save all three settings and power-cycle to clear the latch.
A failed EEPROM readback during saving also latches E3; power-cycle before recovery.
Writes invalidate the marker first and commit it last, so an interrupted write
cannot silently select another direction. Normal saves require no menu; they stop idle peeling and reject active feeds; recovery saves repair an invalid record without clearing the motor fault.

The installed universal bootloader supports this application update unchanged.
Use the normal addressed uploader; do not upload the loader over RS485.
The prepared versioned image can be uploaded later with:

```sh
python tools/rs485_upload.py --port YOUR_PORT --address 9 --firmware build/0.1.1/v485-0.1.1.bin
```
The optional ESP32 bridge source now forwards CONFIG/SETCONFIG too; an older
bridge needs rebuilding for those commands. The direct USB adaptor needs no change.

The saved default event count also has a direct bus setter:

```sh
# 8 mm feeder: two opto events = nominal 4 mm per manual feed or F0 request.
python tools/configure_unit.py --port YOUR_PORT --address 9 --count 2
```

This stores the default in EEPROM byte 1. Explicit F1 still means one event
(nominal 2 mm on the 8 mm type); F0 and the local feed button use the saved count.
SETCOUNT requires a matching UID and count 1–99, needs no menu, verifies the write,
and rejects active feeds. It preserves physical type and both motor directions.

## Advance/retract by items

`tools/jog_items.py` uses the direct USB–RS485 adapter (item jogging is not
forwarded by the ESP32 bridge). It uses the saved default count as **sensor events per item**.
It does not interpret an item count as millimetres. Configure pitch independently
of physical width; only pitches representable by whole sensor events are accepted:

```sh
# This 8 mm feeder: 4 mm/item = 2 events/item.
python tools/configure_unit.py --port YOUR_PORT --address 9 --pitch-mm 4
# Example wider feeder: 12 mm/item = 3 events/item at 4 mm/event.
python tools/configure_unit.py --port YOUR_PORT --address 21 --pitch-mm 12

# Read the plan without moving.
python tools/jog_items.py --port YOUR_PORT --address 9 --direction advance --items 30 --plan
# Execute separately when ready; each command moves the requested number of items.
python tools/jog_items.py --port YOUR_PORT --address 9 --direction advance --items 30
python tools/jog_items.py --port YOUR_PORT --address 9 --direction retract --items 30
```

At 4 mm/item, 30 items is nominally 120 mm / 60 sensor events. A request for
50 items is one continuous 100-event move, not PC batches. Wider tape does not
imply a particular component pitch: set its actual pocket spacing. A 6 mm pitch
on a 4 mm/event wheel cannot be individually resolved and is rejected, rather than
rounded. Direction is relative to the saved normal feed direction; retract never
rewrites EEPROM polarity.

JOG stops and inhibits the peel motor, including idle take-up on wider feeders,
until the next regular feed/manual advance or reset. It accepts up to **10,000
sensor events per request** using 32-bit target/progress counters. The two-digit
display shows the requested item count, capped at 99 for larger requests.

Two independent SysTick guards protect item moves:

- **No progress:** no sensor edge for 3 seconds stops both motors and latches E1.
- **Total deadline:** 2 seconds startup allowance + 1 second per requested sensor
  event. Sensor activity cannot extend this bound. For 50 items at two events/item,
  the ceiling is 102 seconds; the motor stops as soon as all 100 events arrive.

The helper sends one motion packet and waits for its matching DONE. Lost replies
cause STATUS queries only; it never resends movement. Its reply deadline follows
the firmware's event-based bound, with two seconds additional communication margin.
A fault or unknown outcome ends the operation.

An addressed `STOP <nonce>` disables both motors immediately and latches **E4**;
a reset is required before movement resumes. The CLI also requests STOP on Ctrl+C:

```sh
python tools/jog_items.py --port YOUR_PORT --address 9 --stop
```

Counting confirms sensor events, not absolute tape position. Reversal backlash,
optical-edge phase and tape engagement require physical validation; forward then
reverse is not guaranteed to return to an exact pocket position. Stop the stock
host while using this standalone tool; its movement counter counts edges in both
directions, so stock estimates may need reconciling after loading/retracting tape.

## Build

Open this folder in VS Code/PlatformIO, then run:

```sh
pio run -e v485 -e bootloader
```

Every board gets the same `.pio/build/bootloader/firmware.bin` and
`.pio/build/v485/firmware.bin`. Width is saved in EEPROM, not selected at build.
The universal image format is 3; it requires the universal bootloader. Older
width-specific loaders must be replaced over SWD before this application upload.

| Saved width | Nominal tape travel per PA3 rising edge | Peel behaviour |
| --- | --- | --- |
| 8 mm | 2 mm: 30 teeth at 4 mm pitch, 60 optical holes | Peel only during a feed |
| 12 / 16 / 24 mm | 4 mm: 30 teeth at 4 mm pitch, 30 holes | Tension-controlled idle take-up allowed |
| Unconfigured | Unknown | Both motors inhibited |

The wheel dimensions/hole counts were supplied by the owner. They establish the
nominal mapping; actual travel, stopping precision and sensor response still need
physical checks. **F remains an optical-event count**, matching the vendor code.
For 2/4/8/12 mm advances an 8 mm feeder needs 1/2/4/6 events; a wider feeder needs
1/2/3 events for 4/8/12 mm. The wider disk cannot resolve a 2 mm advance. Reel
component spacing sets the event count; tape width alone does not set feed pitch.

## Commission the 30 boards

See [COMMISSIONING.md](COMMISSIONING.md). Initial batch programming uses **ST-Link only**, including EEPROM settings and
startup verification; no RS485 connection or button selection is needed. The plan
is IDs 1–20 at 8 mm, 21–27 at 12 mm, and 28–30 at 16 mm. Connect one commissioning board at a time.
Read-only `TYPE` reports width, saved default event count and nominal micrometres
per event. No type is guessed from the MCU or old EEPROM data.

## Before installing

Pins, timing and version are in [src/config.h](src/config.h). The C/H files are in [src/](src/); the saved physical width selects the motor behaviour.

The build assumes an **STM32F103C8 with 64 KB flash, 20 KB RAM and an 8 MHz crystal**, running at 72 MHz. `bluepill_f103c8` supplies that MCU profile. Check the actual chip and crystal before programming a board.

Install the **8 KB bootloader over ST-Link first**, then upload the application over RS485. The application starts at **0x08002000** and needs the loader’s EEPROM boot record. A binary linked at the start of flash won’t work with this layout. Follow the [installation and update guide](BOOTLOADER.md).

## Wiring

| Function | Pins |
| --- | --- |
| LED | PB5, active low |
| Indexed motor | PA6 / PA7 |
| Peel motor | PA8 / PA12 |
| Feed button | PA4, active low; short tap advances |
| Menu button | PA2, active low; hold opens the menu |
| Peel tension switch | PB6, pull-up input; isolated NC contact to GND |
| Index counter | PA3, rising edge |
| External feed trigger | Removed; PB6 is exclusively the peel-switch input |
| RS485 | PA9 TX, PA10 RX, PA1 direction; 115200 baud, 8N1 |
| 24C02 EEPROM | PB15 SCL, PB14 SDA; ID at byte 0, count at byte 1 |
| CH455 display | PB12 clock, PB13 data |

Driving both control pins of a motor high stops it. PB6 uses the MCU’s internal pull-up; the other existing inputs and EEPROM bus retain their external bias/pull-ups. If you move an interrupt or UART pin, update the board setup and handlers too.

## Direct USB–RS485 host

The [PC host service](../USB_host/README.md) connects a direct auto-direction adapter to OpenPnP over local TCP. It owns the bus, waits for DONE, and provides a local page for basic stock, diagnostics, IDs and updates. The ESP32 controller remains an alternative standalone path. Stock is informational and cannot stop feeding.

The feeder reports a RAM-only movement total and a host-claimed runtime token. Manual advances, powered hand movement and partial feeds are included; MCU resets clear the token so the host can flag uncertain stock. These counters do not write EEPROM. See the [diagnostic protocol](BOOTLOADER.md#protocol-reference).

## Advance commands

With the matching [ESP32-C3 controller 0.1.0 development build](../../V485-Feeder%20Controller/CODE_esp32C3/README.md), send `M600 N7 F4` over USB. The controller waits for completion before returning `ok`. **F counts index-sensor events, not millimetres.** `F0` uses the saved default count of 1–99.

A direct RS485 adapter can still send the legacy `N7 F4` command followed by LF. Operating IDs are 1–99; counts are 0–99. Spaces or tabs and CRLF are accepted; signs and extra fields are rejected. Its replies mean:

- `OK`: accepted, **not finished**.
- `Busy`: already reserved/running, or faulted.
- No reply: the outcome is unknown. **Do not automatically resend**; the tape may have moved.

### Completion replies

The ESP32 uses addressed, CRC-protected packets rather than the legacy replies:

| Request body inside `Bdd … CRC32` | Reply body | Meaning |
| --- | --- | --- |
| `FEED <session> <sequence> <count>` | `ACCEPT <session> <sequence>` | Feed reserved; motor starts after the reply |
| Same request while busy | `BUSY <session> <sequence>` | Request rejected |
| Same request while faulted | `FAULT <session> <sequence>` | Request rejected; fault latched |
| `STATUS <session> <sequence>` | `RUNNING <session> <sequence>` | Matching feed is reserved/running |
| Same status poll | `DONE <session> <sequence>` | Sensor count reached; index motor set idle |
| Same status poll | `FAULT <session> <sequence>` | Matching feed stopped on a motor/settings fault |
| Same status poll | `UNKNOWN <session> <sequence>` | No matching saved request result |

Numeric fields use exactly eight hexadecimal digits. Count is 0–99, with 0 selecting the saved default. A framed FEED addressed to an unassigned feeder at 0 reports FAULT and cannot start a motor. Session and sequence tie replies to their request, so an old ACK cannot confirm a new advance. The CRC and packet format match the [update protocol](BOOTLOADER.md).

The feeder records DONE after the final count and index-motor idle outputs. A motor timeout records FAULT instead. Interrupt handlers never send replies; the main loop answers STATUS polls, so completion packets don’t appear unexpectedly on the shared bus.

The result stays in RAM until another addressed feed is accepted, the feeder ID changes, or the board resets. Manual feeds don’t replace it. It is safe to repeat STATUS after a lost ACCEPT or result reply. A reset returns UNKNOWN. **FEED requests are not deduplicated and must not be retried automatically.** A settings fault still allows STATUS at the unchanged running ID.

## PB6 peel-switch wiring

Retain both original board buttons. PB6 on the unused external-trigger connector
is now the peel-tension input; it cannot request a feed.

- Connect the isolated microswitch **COM to board GND** and **NC to PB6**.
- Keep the existing PB6 10 kΩ pull-up to 3.3 V and 100 nF capacitor to GND, as identified on the received board. Firmware also enables the internal pull-up.
- Reconnect the peel motor through its original driver without the switch in series. Never connect motor voltage to PB6. Do not connect the old external trigger to this connector.
- Leave the PA2 and PA4 buttons installed. SWDIO/SWCLK remain available.

A closed contact permits peeling. An open contact means tension reached or a
broken wire. Firmware samples PB6 every 1 ms and stops peeling when it reads
open; the existing RC filter also affects physical response time. Restart needs
a contact closed for at least 20 ms and at least 100 ms since the last stop.
Sampling stays active during display writes and serial waits. Stopping peel does
not stop index movement or counting.

The 8 mm build stops both motors between advances. The wider build permits
idle take-up only while the switch permits it. Both stay stopped during startup,
menus, updates and faults. Polarity and timing are in [config.h](src/config.h);
actual switch and motor behaviour still need bench validation.

## PA4 feed button, PA2 menu and saved settings

Short-tap PA4 to advance using the saved default count; holding PA4 does not open a menu or feed on release. PA4 cannot edit settings.

Hold PA2 to choose a function:

| Hold time | Display | Release to select |
| --- | --- | --- |
| 2–4 seconds | `01` | Accept an ID over RS485 |
| 4–6 seconds | `02` | Enter the bootloader and wait for an update |
| 6–8 seconds | `03` | Edit the feeder ID locally |
| 8–10 seconds | `04` | Edit the default feed count |
| 10–12 seconds | `05` | Set physical width: 08 / 12 / 16 / 24 |

Keep holding to cycle back through the menu. A hold release never advances the tape. The display shows the function number while selecting; once in `03`/`04`/`05`, it flashes the value being edited. Tap PA2 to increment, wrapping IDs and counts through 1–99; width cycles 08 → 12 → 16 → 24 → 08. An unassigned feeder starts the ID editor at `01`. **Hold PA2 for two seconds, then release to save and exit.** Values stay temporary until saved. Twenty seconds without a press cancels an edit without writing EEPROM.

`01` flashes until an ID is assigned, a two-second PA2 hold is released to cancel, or its 20-second window expires. `02` records an update request and resets into the loader; it does not erase flash. A motor fault still permits menu `02`, but cannot be cleared by editing settings. An EEPROM fault requires reset/inspection.

Entering a menu stops both motors. Serial feeds return BUSY and PA4 presses are consumed until normal operation resumes. A press beginning during a feed cannot become an advance/menu action when that feed finishes. Either button held at power-up must be released before it can act. Menu timing and display feedback never block serial processing.

### Set an ID from the PC

Close OpenPnP and other serial tools. Select `01` with PA2 on the feeder, then run from this folder:

```sh
# Current ID 7 -> new ID 12, through the controller USB port or a direct adapter.
python tools/assign_id.py --port COM5 --address 7 --new-id 12
```

Use the matching controller build: it forwards the new `IDENT`/`SETID` packets. The tool checks local arming, probes the proposed ID for a responding application or bootloader, targets the selected MCU's hardware UID, and confirms that same UID at the new ID after saving. A lost save acknowledgement triggers verification, never an automatic second SETID. After closing the tool, wait 10 seconds for the controller's update/settings interlock before feeding.

Only one unassigned feeder at address 0 may be connected for programming. Remote assignment rejects a new ID of 0 before sending anything. Keep all bus IDs unique. The probe can detect responding devices running this local firmware; it cannot reserve an ID belonging to an unplugged, unpowered, faulty or stock-firmware feeder. Local menu `03` does not check for duplicates on the bus.

New settings take effect only after an EEPROM write passes readback. If it fails, both motors stop, the display shows **E3**, and feed/update commands stay disabled until reset; read-only STATUS, IDENT and DIAG still work. This avoids running with an uncertain saved ID.

At startup, failed reads are retried with both motors stopped and E3 displayed. They never become ID 0 or overwrite settings. Only a successfully read blank ID (`FF`) is written back as `0`. Both `0` and that normalised blank state flash **00** continuously in normal operation. Neither motor can run, and manual and serial advances are rejected until a valid ID **1–99** and physical width have been saved. The same unassigned indication flashes while waiting in the bootloader; upload progress takes over during a transfer. Menu `03` or locally armed menu `01` can program an ID, and updates can use reserved transport address `0`; it is never an operating feeder ID. An invalid saved ID also blocks operation until corrected. An invalid default count becomes the positive default after a checked read and verified write.

Serial monitoring needs an RS485 adapter at 115200 baud with LF endings. ST-Link alone does not provide a serial console.

## Flash a feeder to locate it

`LOCATE <nonce>` is addressed and CRC-protected like `IDENT`. It replies
`LOCATING <nonce>` and flashes the ID/display and board LED for about four
seconds. Both motors remain stopped during location; feed requests report BUSY.
A running feed, fault or menu reports BUSY instead of starting the indication.
`IDENT` stays read-only and never flashes.

## Motor timeout and updates

`FEED_TIMEOUT_MS` allows **10 seconds total by default for ordinary/manual feeds**.
Item-count JOG moves instead use the progress and scaled total guards above. Exceeding it stops both motors and latches E1 until reset. Manual triggers cannot restart the feed. Framed commands/status report FAULT; legacy feeds return Busy. Inspect the mechanism before resetting, and check the timeout against real loads and counts.

`PEEL_TIMEOUT_MS` separately limits one uninterrupted peel run to **10 seconds**. Exceeding it also stops both motors and latches E2, including during idle on wider feeders. A switch opening stops peeling immediately rather than waiting for that deadline.

Updates address one feeder ID at a time and preserve its ID/count. Batch uploads finish one ID before moving to the next. See [BOOTLOADER.md](BOOTLOADER.md) for installation, recovery and upload commands.

## Check without hardware

Run `python tools/check_feeder.py` with Python and a native `gcc` compiler. It compiles the real sources with simulated hardware and checks both widths, including feed races, serial framing, settings, buttons, sensor completion, faults and deadlines. Run `python tools/rs485_upload.py --self-check` for the uploader’s offline image/packet checks and lost-initial-reply case. Run `python tools/assign_id.py --self-check` for remote assignment, occupied IDs and lost-save-ACK checks. These checks open no hardware ports.
