# V485 feeder firmware — 8/12/16/24 mm

> Designs and original files by [MicroSMT](https://github.com/microsmt/Bing-feeder). [Credits and local changes](../../../CREDITS.md).

Both feeder variants share this STM32 HAL/PlatformIO project. **Version 0.1.0 is still in development: it builds and passes simulated checks, but no real feeder or controller has been programmed or tested with it.** See the [changelog](CHANGELOG.md) for the work so far.

## Build

Open this `CODE_feeder` folder in VS Code with PlatformIO. Choose the feeder width under **Project Tasks → Build**, or run:

```sh
pio run -e v485_8mm
# Or, for wider feeders:
pio run -e v485_12_16_24mm
```

| Environment | Motor behaviour |
| --- | --- |
| `v485_8mm` (default) | Peel runs only during a feed and only while the tension switch permits it; both motors stop between feeds |
| `v485_12_16_24mm` | Index motor stops between feeds; tension-controlled peeling is also allowed during normal idle |

The wider build covers 12, 16 and 24 mm. Build outputs are `.pio/build/<environment>/firmware.bin` and `firmware.elf`; Git ignores them. Package versions are pinned in [platformio.ini](platformio.ini).

## Before installing

Pins, timing and version are in [src/config.h](src/config.h). The C/H files are in [src/](src/); choosing the build environment selects the motor behaviour.

The build assumes an **STM32F103C8 with 64 KB flash, 20 KB RAM and an 8 MHz crystal**, running at 72 MHz. `bluepill_f103c8` supplies that MCU profile. Check the actual chip and crystal before programming a board.

Install the **8 KB bootloader over ST-Link first**, then upload the application over RS485. The application starts at **0x08002000** and needs the loader’s EEPROM boot record. A binary linked at the start of flash won’t work with this layout. Follow the [installation and update guide](BOOTLOADER.md).

## Wiring

| Function | Pins |
| --- | --- |
| LED | PB5, active low |
| Indexed motor | PA6 / PA7 |
| Peel motor | PA8 / PA12 |
| Control button | PA4, active low; tap advances, hold opens the menu |
| Peel tension switch | PA2, internal pull-up; isolated NC contact to GND |
| Index counter | PA3, rising edge |
| External feed trigger | PB6, rising edge |
| RS485 | PA9 TX, PA10 RX, PA1 direction; 9600 baud, 8N1 |
| 24C02 EEPROM | PB15 SCL, PB14 SDA; ID at byte 0, count at byte 1 |
| CH455 display | PB12 clock, PB13 data |

Driving both control pins of a motor high stops it. PA2 uses the MCU’s internal pull-up; the other existing inputs and EEPROM bus retain their external bias/pull-ups. If you move an interrupt or UART pin, update the board setup and handlers too.

## Advance commands

With the matching [ESP32-C3 controller 0.1.0 development build](../../V485-Feeder%20Controller/CODE_esp32C3/README.md), send `M600 N7 F4` over USB. The controller waits for completion before returning `ok`. **F counts index-sensor events, not millimetres.** `F0` uses the saved default count of 1–99.

A direct RS485 adapter can still send the legacy `N7 F4` command followed by LF. IDs/counts are 0–99. Spaces or tabs and CRLF are accepted; signs and extra fields are rejected. Its replies mean:

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

Numeric fields use exactly eight hexadecimal digits. Count is 0–99, with 0 selecting the saved default. Session and sequence tie replies to their request, so an old ACK cannot confirm a new advance. The CRC and packet format match the [update protocol](BOOTLOADER.md).

The feeder records DONE after the final count and index-motor idle outputs. A motor timeout records FAULT instead. Interrupt handlers never send replies; the main loop answers STATUS polls, so completion packets don’t appear unexpectedly on the shared bus.

The result stays in RAM until another addressed feed is accepted, the feeder ID changes, or the board resets. Manual/external feeds don’t replace it. It is safe to repeat STATUS after a lost ACCEPT or result reply. A reset returns UNKNOWN. **FEED requests are not deduplicated and must not be retried automatically.** A settings fault still allows STATUS at the unchanged running ID.

## PA2 peel-switch wiring

This build needs the proposed wiring modification. The stock inline motor switch must become a **dry contact input**, isolated from the motor circuit:

- Connect the switch's **COM to board GND** and **NC to PA2**, using the old PA2 button's signal pad. Use the schematic or continuity checks to identify signal and ground pads; some tactile-button pads are internally joined.
- Reconnect the peel motor through its original motor driver without the switch in series. Never connect a motor lead or motor voltage to PA2.
- Remove the old PA2 button, or leave it unused: pressing it now simulates a closed tension contact. SWDIO/SWCLK remain available for programming/debugging.

The existing PA2 resistor/filter stays in place; firmware also enables the internal pull-up. A closed contact permits peeling. An open contact means tension reached, or a broken wire. Firmware samples PA2 every 1 ms and stops peeling as soon as it reads open. Restart needs a contact closed for at least 20 ms and at least 100 ms since the motor last stopped. Tension sampling stays active during display writes and serial waits. Stopping the peel motor does not stop the index motor or its counting.

The 8 mm build still stops both motors between advances. The wider build can take up slack while idle, but only when the switch permits it. Both stay stopped during startup, menus, updates and faults. Pin, polarity, debounce, restart delay and continuous-run limit are in [config.h](src/config.h); the proposed NC wiring and timing still need checking on a real feeder.

## PA4 button and saved settings

Tap PA4 to advance using the saved default count. Hold it to choose a function:

| Hold time | Display | Release to select |
| --- | --- | --- |
| 2–4 seconds | `01` | Accept an ID over RS485 |
| 4–6 seconds | `02` | Enter the bootloader and wait for an update |
| 6–8 seconds | `03` | Edit the feeder ID locally |
| 8–10 seconds | `04` | Edit the default feed count |

Keep holding to cycle back through the menu. A hold release never advances the tape. The display shows the function number while selecting; once in `03`/`04`, it flashes the value being edited. Tap to increment, wrapping IDs through 0–99 and counts through 1–99. **Hold for two seconds, then release to save and exit.** Values stay temporary until saved. Twenty seconds without a press cancels an edit without writing EEPROM.

`01` flashes until an ID is assigned, a two-second hold is released to cancel, or its 20-second window expires. `02` records an update request and resets into the loader; it does not erase flash. A motor fault still permits menu `02`, but cannot be cleared by editing settings. An EEPROM fault requires reset/inspection.

Entering a menu stops both motors. Serial feeds return BUSY and external triggers are ignored until normal operation resumes. A press beginning during a feed cannot become an advance/menu action when that feed finishes. A button held at power-up must be released before it can act. Menu timing and display feedback never block serial processing.

### Set an ID from the PC

Close OpenPnP and other serial tools. Select `01` on the feeder, then run from this folder:

```sh
# Current ID 7 -> new ID 12, through the controller USB port or a direct adapter.
python tools/assign_id.py --port COM5 --address 7 --new-id 12
```

Use the matching controller build: it forwards the new `IDENT`/`SETID` packets. The tool checks local arming, probes the proposed ID for a responding application or bootloader, targets the selected MCU's hardware UID, and confirms that same UID at the new ID after saving. A lost save acknowledgement triggers verification, never an automatic second SETID. After closing the tool, wait 10 seconds for the controller's update/settings interlock before feeding.

Only one commissioning feeder at ID 0 may be connected. Keep all bus IDs unique. The probe can detect responding devices running this local firmware; it cannot reserve an ID belonging to an unplugged, unpowered, faulty or stock-firmware feeder. Local menu `03` does not check for duplicates on the bus.

New settings take effect only after an EEPROM write passes readback. If it fails, both motors stop, the display shows **EE**, and feed/update commands stay disabled until reset; read-only STATUS and IDENT still work. This avoids running with an uncertain saved ID.

At startup, failed reads are retried with both motors stopped and EE displayed. They never become ID 0 or overwrite settings. Only a successfully read blank ID uses commissioning ID 0. An invalid saved ID also blocks operation until corrected. An invalid default count becomes the positive default after a checked read and verified write.

Serial monitoring needs an RS485 adapter at 9600 baud with LF endings. ST-Link alone does not provide a serial console.

## Motor timeout and updates

`FEED_TIMEOUT_MS` allows **10 seconds total by default**. Exceeding it stops both motors and latches EE until reset. Manual/external triggers cannot restart the feed. Framed commands/status report FAULT; legacy feeds return Busy. Inspect the mechanism before resetting, and check the timeout against real loads and counts.

`PEEL_TIMEOUT_MS` separately limits one uninterrupted peel run to **10 seconds**. Exceeding it also stops both motors and latches a fault, including during idle on wider feeders. A switch opening stops peeling immediately rather than waiting for that deadline.

Updates address one feeder ID at a time and preserve its ID/count. Batch uploads finish one ID before moving to the next. See [BOOTLOADER.md](BOOTLOADER.md) for installation, recovery and upload commands.

## Check without hardware

Run `python tools/check_feeder.py` with Python and a native `gcc` compiler. It compiles the real sources with simulated hardware and checks both widths, including feed races, serial framing, settings, buttons, sensor completion, faults and deadlines. Run `python tools/rs485_upload.py --self-check` for the uploader’s offline image/packet checks and lost-initial-reply case. Run `python tools/assign_id.py --self-check` for remote assignment, occupied IDs and lost-save-ACK checks. These checks open no hardware ports.
