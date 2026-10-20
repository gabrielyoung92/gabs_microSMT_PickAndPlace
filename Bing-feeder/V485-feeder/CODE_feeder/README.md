# V485 feeder firmware — 8 mm and 12/16/24 mm

> **Original: [MicroSMT / Bing-feeder](https://github.com/microsmt/Bing-feeder).** [Credits and local changes](../../../CREDITS.md).

Plain C PlatformIO firmware, version **0.3.0**, adapted from MicroSMT's V485 sources using STM32 HAL. Both feeder variants share one project. **Builds and simulated checks pass; physical hardware is untested.** See the [changelog](CHANGELOG.md) for validation details.

## Build

Open **this CODE_feeder folder** in VS Code with PlatformIO. Choose an environment under **Project Tasks → Build**, or use its terminal:

```sh
pio run -e v485_8mm
# Or, for wider feeders:
pio run -e v485_12_16_24mm
```

| Environment | Motor behaviour |
| --- | --- |
| `v485_8mm` (default) | Both motors stop between feeds |
| `v485_12_16_24mm` | Indexed motor stops between feeds; peel motor runs continuously during normal idle |

The wider build covers 12, 16 and 24 mm. Outputs are `.pio/build/<environment>/firmware.bin` and `firmware.elf`; build files are ignored by Git. Dependencies are pinned in [platformio.ini](platformio.ini).

## Configure and install

Edit [src/config.h](src/config.h) for pins, timing and version. All C/H sources are in [src/](src/). Environment selection sets the width behaviour.

The target assumes **STM32F103C8, 64 KB flash, 20 KB RAM and an 8 MHz crystal**, running at 72 MHz. `bluepill_f103c8` is the MCU profile; confirm the actual feeder chip and crystal before installation.

Install the **8 KB bootloader with ST-Link first**, then send the application over RS485. The application starts at **0x08002000** and needs the loader's EEPROM boot record; older binaries linked at flash base are incompatible. Follow the [installation and update guide](BOOTLOADER.md).

## Wiring

| Function | Pins |
| --- | --- |
| LED | PB5, active low |
| Indexed motor | PA6 / PA7 |
| Peel motor | PA8 / PA12 |
| Buttons | PA2 increment/manual feed; PA4 decrement |
| Index counter | PA3, rising edge |
| External feed trigger | PB6, rising edge |
| RS485 | PA9 TX, PA10 RX, PA1 direction; 9600 baud, 8N1 |
| 24C02 EEPROM | PB15 SCL, PB14 SDA; ID at byte 0, count at byte 1 |
| CH455 display | PB12 clock, PB13 data |

Both motor control pins high means stop. Inputs and the EEPROM bus rely on the PCB's external bias/pull-ups. Moving interrupt or UART pins also requires changes to the board setup and handlers.

## Commands and buttons

Send `N7 F4` followed by LF to request four index events from feeder 7. Address/count are 0–99; `F0` uses the saved default count of 1–99. CRLF and separating spaces/tabs are accepted; signs and extra fields are rejected.

- `OK`: command accepted, **not feed completed**.
- `Busy`: feed already reserved/running, or a fault is latched.
- Lost reply: outcome unknown. **Do not automatically resend a feed**; it may already have moved the tape.

Hold PA4 for three seconds to enter/exit ID adjustment, or PA2 for count adjustment. Short PA2/PA4 presses increase/decrease the setting. In normal mode, a short PA2 press feeds once. ID/count are saved in EEPROM; the button UI does not report a failed save.

Serial monitoring needs an RS485 adapter, at 9600 baud with LF endings. ST-Link alone provides no serial connection.

## Timeout and updates

A feed exceeding `FEED_TIMEOUT_MS` (**10 seconds total by default**) stops both motors and latches an **EE** fault until reset. Manual/external triggers cannot restart it; serial feeds return `Busy`. Inspect the mechanism before resetting. Validate the timeout against real feed loads/counts; it is an initial software limit.

Firmware updates select a destination ID and preserve its saved ID/count. Batch uploads update one ID at a time. Use [BOOTLOADER.md](BOOTLOADER.md) for installation, recovery and upload commands.
