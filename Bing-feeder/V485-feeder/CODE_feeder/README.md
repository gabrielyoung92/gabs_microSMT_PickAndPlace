# V485 feeder firmware 0.1.3

See [EEPROM.md](../../../EEPROM.md) for the byte layout, setting ranges and
which reel/part values live on the computer.

One STM32 application for this machine's 8/12/16/24 mm powered feeders. Width,
ID, advance count, motor directions and switch polarity are saved per unit.
The installed bootloader handles application updates over RS485.

Original feeder designs and firmware are by [MicroSMT](https://github.com/microsmt/Bing-feeder).
Local changes were prepared by Gab with ChatGPT assistance. See [credits](../../../CREDITS.md).

## Build and update

Open this folder in PlatformIO or run:

```sh
pio run -e v485
```

This builds `.pio/build/v485/firmware.bin` and automatically packages it as
`../USB_host/firmware.json`. Deploy that bundle to the machine computer, then
use the dashboard's **Update** or **Update all outdated**. No binary selection
or bootloader reprogramming is needed for normal updates. The host verifies the
application CRC and preserves saved feeder settings.

- [Dashboard and OpenPnP setup](../USB_host/README.md)
- [Update protocol and direct uploader](BOOTLOADER.md)
- [Initial ST-Link programming](COMMISSIONING.md)
- [Current firmware notes](CHANGELOG.md)

Building does not flash hardware. The target is STM32F103C8, 64 KB flash,
20 KB RAM and an 8 MHz crystal. PlatformIO pins STM32 platform 20.0.0,
STM32CubeF1 1.8.7 and GCC 14.2.1. It uses HAL/CMSIS; CubeMX is not required.

## Source layout

| File | Purpose |
| --- | --- |
| `src/config.h` | Version, pins, timeouts and defaults |
| `src/feeder.c` | Motor control, buttons, optical counting and addressed commands |
| `src/bootloader.c` | Application loader and update protocol |
| `src/board.c`, `src/eeprom.c` | Hardware setup and saved settings |
| `tools/rs485_upload.py` | Application inspection and serial uploader |
| `tools/configure_unit.py` | Read/save directions, polarity and default advance |
| `tools/assign_id.py` | UID-targeted bus ID assignment |
| `tools/jog_items.py` | Bench advance/retract by whole items |
| `tools/flash_swd.py` | Initial SWD loader/application/settings programming |
| `tools/bundle_dashboard.py` | PlatformIO hook for the dashboard firmware bundle |

## Feed and peel behaviour

The index motor stops when the requested optical event count is reached.
All widths use the same peel control: the switch requests take-up, the peel
motor runs, and reaching tension stops it. **At startup peel stays off until
the first ordinary feed command or feed-button press.** It then works during
indexing and while idle. Only the optical distance per event differs by width.

The peel motor has a separate **ten-second continuous-run timeout**. Menus,
settings writes, faults and input test mode inhibit peeling. Item jogs and
Clear error hold peel stopped until the next ordinary feed. Restart returns
to the same unarmed startup state.

**Clear error** clears runtime index-timeout, peel-timeout and Stop faults
without rebooting, moving tape or writing EEPROM. It refuses active movement
and menus. Invalid settings remain blocked until corrected. Configure can
repair an invalid options record and save width/count while E3 remains latched;
Clear Error follows successful repair. Failed EEPROM writes remain blocked.

The independent hardware watchdog resets a stalled application after roughly
four seconds. Only main-loop progress refreshes it; interrupts do not. Motors
start stopped after a reset and no interrupted feed is replayed. Saved settings
and the bootloader are unchanged.

On startup, a feeder sends one CRC-checked `ONLINE uid0 uid1 uid2` packet after
an ID-based delay. This is best-effort notification, without acknowledgement or
retry. The host prioritises its next poll; missed packets still use ordinary
discovery. Regular status/heartbeat traffic remains polled.

| Width | Sensor distance/event | Default events | Default advance |
| --- | --- | --- | --- |
| 8 mm | 2 mm | 2 | 4 mm |
| 12 / 16 / 24 mm | 4 mm | 1 | 4 mm |

Tape width is not part spacing. Set the advance to match the tape's pockets.
`F0` and the local feed button use the saved count; an explicit `F4` means four
optical events, not 4 mm. The dashboard edits spacing in millimetres and converts
it to events. Sensor geometry and loaded tape travel need bench verification.

## Motors and tension switch

EEPROM stores feed reversal, peel reversal and NC/NO polarity independently.
Defaults are reversed feed / normal peel / NC on 8 mm units, and normal feed /
normal peel / NC on wider units. Valid saved settings survive updates.

The isolated tension switch connects **PB6 to GND**. Keep both local buttons.

| Polarity | PB6 LOW / contact closed | PB6 HIGH / contact open |
| --- | --- | --- |
| NC | Requests peel | Stops peel |
| NO | Stops peel | Requests peel |

With NO selected, a disconnected switch also requests peeling. Directions change
run outputs while retaining stop/brake behaviour. Ordinary feeds have a ten-second
index timeout. Faults stop both motors and remain latched until reset:

| Display | Meaning |
| --- | --- |
| `00` flashing | Unassigned; motors inhibited |
| `E1` | Index/feed timeout |
| `E2` | Peel timeout |
| `E3` | Saved settings/EEPROM failure |
| `E4` | Explicit STOP received |

Correct the physical problem before resetting. A settings repair is verified
before use; an existing fault still requires a reset. The display is not a
measurement of tape position or successful pickup.

## Motor-off input test

Use the dashboard's **Test** popup to enter the latched input test. Both motors
and local feeding stay inhibited while it reports raw switch contact,
interpreted peel request, button states, optical input/total, switch transition
count and uptime. Closing the popup does not end test mode. Explicit **End test**
or a power cycle ends it; fault latches are retained. Wider feeders may resume
idle peeling after exit only if a normal feed had already armed take-up.

The host reads state through addressed packets. There are no unsolicited bus
heartbeats. Normal `DIAG` polling supplies state and movement counts; the active
input-test popup reads more frequently. No telemetry writes EEPROM.

## Local buttons

**PA4** short press feeds the saved advance. Hold **PA2** and release at the
required menu number:

| Hold | Menu | Action |
| --- | --- | --- |
| 2–4 s | `01` | Permit remote bus ID assignment |
| 4–6 s | `02` | Enter bootloader |
| 6–8 s | `03` | Edit ID |
| 8–10 s | `04` | Edit default optical event count |
| 10–12 s | `05` | Edit width: 08 / 12 / 16 / 24 |

In an editor, tap PA2 to change the value; hold for two seconds and release to
save. Twenty seconds without a press cancels. Menus stop motors and reject
feeds. Held-at-startup or overlapping button presses do not become delayed feeds.

Bus IDs must be unique, 1–99. Address 0 is for one unassigned unit at a time.
Only ID reassignment requires menu 01; motor/switch/count configuration does not.

## Direct serial tools

The dashboard must release the adapter before standalone tools can use it.
Use 115200 8N1 through the direct auto-direction USB–RS485 adapter.
From this folder:

```sh
# Read without moving motors.
python3 tools/configure_unit.py --port YOUR_PORT --address 7

# Save directions/polarity and verify readback.
python3 tools/configure_unit.py --port YOUR_PORT --address 7 --feed reversed --peel normal --switch nc

# Two sensor events = 4 mm on an 8 mm feeder.
python3 tools/configure_unit.py --port YOUR_PORT --address 7 --count 2

# Select menu 01 on this feeder before assigning its new ID.
python3 tools/assign_id.py --port YOUR_PORT --address 7 --new-id 12

# Application update using the existing bootloader.
python3 tools/rs485_upload.py --port YOUR_PORT --address 7 --firmware .pio/build/v485/firmware.bin
```

The tools target the hardware UID where settings are changed, send saves once
and verify readback. Keep destination IDs unique, including unplugged units.
See `python3 tools/jog_items.py --help` for explicit bench item moves. Jog uses
32-bit progress, a three-second no-progress guard and a scaled total bound.
Ctrl+C sends STOP, which latches E4. Neither tools nor host automatically replay
an advance after an ambiguous reply.

`LOCATE` is available in the addressed protocol to flash the ID and LED for
about four seconds with motors stopped. It is not a dashboard button.

## Software checks

```sh
python3 tools/check_feeder.py
python3 tools/check_watchdog.py
python3 tools/rs485_upload.py --self-check
python3 tools/assign_id.py --self-check
python3 tools/configure_unit.py --self-check
```

These compile/run real C logic with simulated hardware or check packet/upload
behaviour; native `gcc` and `g++` are required. They cover motors-off test
mode, peel completion, switch handling, settings, buttons, UART, completion,
timeouts and uploader recovery. They do not prove loaded tape or pickup accuracy.
Application 0.1.3 image CRC and startup inhibition have been verified on
connected bench units: motors stayed stopped and fault-free beyond the peel
timeout. Watchdog reset timing and loaded tape/switch behaviour need bench checks.
