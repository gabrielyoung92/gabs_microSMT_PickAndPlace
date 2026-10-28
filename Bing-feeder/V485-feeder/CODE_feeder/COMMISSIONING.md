# V485 universal commissioning

The example 30-board commissioning profile is: **IDs 1–20 = 8 mm; 21–27 = 12 mm;
28–30 = 16 mm.** Only verified boards are added to the local `units.json` ledger.

## ST-Link only: initial batch programming

Connect one board to ST-Link SWDIO/SWCLK/GND/3.3 V at a time. Keep motors
unpowered. **RS485 and button presses are not needed for this procedure.**

Build once from this folder:

```sh
pio run -e v485 -e bootloader
```

Then select the desired ID explicitly:

```sh
python tools/flash_swd.py --stlink STLINK_SERIAL --new-id 2
```

The width comes from the batch plan above. `--width 24` can override it for
another feeder. `--count` selects the saved default optical-event count; it is
1 unless specified. That means a nominal 2 mm manual feed on an 8 mm feeder,
or 4 mm on a wider feeder. Adjust per reel/job later.

The tool reads the physical MCU UID and backs up its original 64 KB flash,
checks the local ledger for reused IDs/boards, installs and readback-verifies
both common images, then calls the real bootloader's EEPROM driver over GDB.
It backs up/read-verifies EEPROM bytes 0–63, saves the ID/count/width and width
check byte, and commits the image boot record last. It then resets into the real
application and verifies the selected ID, type, count, ready/idle state, no
fault and stopped motor outputs before leaving the MCU running.

Only successful boards enter the repository's ignored `.local/v485-batch/units.json`.
Logs, images of original flash/settings and per-unit reports stay beside it.
After each success, check the steady display ID, disconnect that board, connect
the next and increment `--new-id`. Do not swap boards during a command.

## RS485 later

The same universal firmware supports application updates, type/ID settings and
visual LOCATE over RS485 at 115200 8N1. Use one commissioning board at a time:

```sh
python tools/commission.py --port /dev/serial/by-id/ADAPTER --address 0 --new-id 2
```

This uploads the application over RS485 and waits for PA2 menu 01 before saving
settings. Hold PA2 for 2–4 seconds and release at 01. An already assigned feeder
uses its current address. `--configure-only` skips the upload. The optional
`--install-loader --stlink STLINK_SERIAL` installs the loader over SWD first.
The ST-Link-only procedure above is preferred for this initial batch.

COM/NC of the isolated tension switch go to GND/PB6. Keep both PA2/PA4 buttons.
Actual switches, tape travel and motor operation still need physical testing.

## Buttons and pitch

PA4 short tap feeds the saved default event count. PA2 holds select: 01 remote
commissioning, 02 update, 03 ID, 04 default count, 05 width. Menu 05 cycles
08/12/16/24. Hold PA2 for two seconds and release to save an edited value.

The original vendor firmware counted PA3 rising edges with no mm conversion.
The supported wheel profile has 30 teeth at 4 mm pitch: 60 optical holes on 8 mm
feeders give nominal 2 mm/event; 30 holes on wider feeders give 4 mm/event.
Thus a 4 mm component pitch needs F2 on an 8 mm feeder or F1 on a wider feeder.
Set feed count per reel/job; physical width does not determine component spacing.

`TYPE <nonce>` returns width, default count and nominal micrometres/event.
`IDENT <nonce>` reads the MCU UID. `LOCATE <nonce>` flashes the addressed ID and
LED for about four seconds without a feed; it refuses while busy/in a menu.
All commands use the existing Bdd/CRC32 framing. See [BOOTLOADER.md](BOOTLOADER.md).

The 8 mm commissioning profile is reversed feed / normal peel / NC and count 2
(4 mm per item). Wider profiles retain normal feed / normal peel / NC and count 1
(4 mm per item). `flash_swd.py --count` can override the event count explicitly.
