# ESP32-C3 feeder controller

> Designs and original files by [MicroSMT](https://github.com/microsmt/Bing-feeder). [Credits and local changes](../../../CREDITS.md).

This is the local PlatformIO version of MicroSMT’s V25 RS485 controller. It sends advance commands to the feeders and passes firmware updates from USB to the RS485 bus.

**Version 0.1.0 is still in development. No real controller or feeder has been programmed or tested with this firmware.** The [changelog](CHANGELOG.md) lists the work and software checks so far.

## Build

Open this `CODE_esp32C3` folder in VS Code with PlatformIO, then choose **Project Tasks → esp32c3 → Build**. From a terminal:

```sh
pio run -e esp32c3
```

The firmware is in [src/main.cpp](src/main.cpp). Pins, speeds and timeouts are in [src/config.h](src/config.h), and the board and USB settings are in [platformio.ini](platformio.ini). Build files go into `.pio/build/esp32c3/`, which Git ignores.

## Board and wiring

The [supplied photo](esp32c3%20%20mini.bmp) shows an ESP32-C3 Super Mini. The build uses the `esp32-c3-devkitm-1` profile for a 4 MB C3. Check the actual module, pinout and flash size before uploading.

| Connection | Setting |
| --- | --- |
| USB console | Native USB CDC, 115200 baud, LF |
| RS485 UART0 RX / TX | GPIO20 / GPIO21, 9600 baud, 8N1 |
| RS485 direction | GPIO9, also BOOT |
| ACK / run indicators | GPIO7 / GPIO8 |

Native USB leaves UART0 free for the feeder bus. Keep `monitor_speed` and the USB baud setting in `config.h` the same.

**MicroSMT says to power the expansion board first.** Its MAX3485 can otherwise stop the C3 from booting. GPIO9 also selects boot mode, so check that wiring carefully.

## Upload and monitor

Once the board is ready, use PlatformIO’s Upload and Monitor tasks, or:

```sh
pio run -e esp32c3 -t upload --upload-port COM7
pio device monitor -e esp32c3 --port COM7
```

Use your controller’s port instead of COM7. If it won’t enter download mode, hold BOOT, press and release RESET, then release BOOT and try again.

## Advance a feeder

Send `M600 N12 F4` or `N12 F4`, followed by a newline. `N` is the feeder’s saved ID. `F` is the number of index-sensor events to count, **not millimetres**. `F0` uses that feeder’s saved default. IDs and counts are 0–99; use the advance count that matches your feeder and tape pitch.

The command accepts upper/lower case, spaces or tabs, and LF or CRLF endings. Extra fields and malformed values are rejected.

The controller sends the advance **once**, then checks its result with read-only `STATUS` requests. It returns `ok N12 F4` only when the feeder reports that the requested count was reached and the index motor was set to idle. `ACCEPT` and `RUNNING` are not success replies. The wider feeders may peel during normal idle, gated by their PA2 tension switch. The index count defines advance completion.

Busy, faults, a lost request record after reset, or a completion timeout return `error: ...` without `ok`. **Don’t blindly resend an advance after a missing reply:** the tape may already have moved. Status requests can be repeated safely; advances cannot. Repeated advance requests are not deduplicated.

Use matching **0.1.0 development builds** of the feeder and controller with the FEED/STATUS protocol. An acceptance-only draft cannot report completion. Each reply must match the feeder ID, controller startup session and request sequence, with a valid CRC. Bare `OK` and old or wrong-feeder replies are ignored. Reaching the sensor count still needs checking against real tape movement and part presentation.

### Timeouts

USB commands allow 32 bytes before the newline and a one-second gap between bytes. Each RS485 reply allows 79 bytes before the newline and a 300 ms response window. Status is polled every 100 ms after a response or wait. The whole advance has a 12-second completion timeout, leaving a margin around the feeder’s 10-second motor deadline. Keep these settings aligned if you change them.

### OpenPnP 2.6 commands

[ReferenceAutoFeeder](https://github.com/openpnp/openpnp/blob/2.6/src/main/java/org/openpnp/machine/reference/feeder/ReferenceAutoFeeder.java) calls an actuator with the feeder’s numeric value. [GcodeDriver](https://github.com/openpnp/openpnp/blob/2.6/src/main/java/org/openpnp/machine/reference/driver/GcodeDriver.java) inserts that value into `ACTUATE_DOUBLE_COMMAND` and waits for its confirmation. M600 is the command used by this controller; OpenPnP lets you choose the command text.

| Actuator command | What the numeric value means |
| --- | --- |
| `M600 N{IntegerValue} F0` | Feeder ID; use its saved advance count |
| `M600 N{IntegerValue} F4` | Feeder ID; request four sensor events |
| `M600 N{Index} F{IntegerValue}` | Sensor-event count; the actuator’s Index holds the feeder ID |

Use `^ok(?:\s.*)?$` for confirmation and `(?i)^error:.*$` for errors. Allow at least 15,000 ms for completion.

The regular **GcodeDriver** waits for the reply before returning from actuation, so this controller needs no extra M400 or fixed feed delay. **GcodeAsyncDriver** queues commands instead; it needs a separate completion wait before picking. A delayed ACK alone won’t make an asynchronous call wait.

## Update feeders over USB

The update path is **PC USB → ESP32-C3 → RS485 → feeder**. The feeder needs the matching local bootloader installed over SWD first; stock vendor firmware cannot accept these updates. See the [feeder update guide](../../V485-feeder/CODE_feeder/BOOTLOADER.md).

Close OpenPnP and serial monitors before updating. Use one RS485 master. Run these from the feeder’s `CODE_feeder` folder:

```sh
# COM7 is the controller USB port; 7 is the feeder's unique ID.
python tools/rs485_upload.py --port COM7 --address 7 --firmware .pio/build/v485_8mm/firmware.bin
# Or update explicit IDs sequentially, all using the same width variant.
python tools/rs485_upload.py --port COM7 --addresses 7,8,9 --firmware .pio/build/v485_8mm/firmware.bin
```

The bridge passes complete, CRC-valid `INFO`, `BOOT`, `HELLO`, `BEGIN`, `DATA`, `END`, `IDENT` and `SETID` packets and replies without changing their bytes, destination or checksum. The PC uploader handles retries, width and memory checks, flash writes and final verification; no separate bridge-mode command is needed.

Update packets can use 127 bytes before the newline. Invalid packets are dropped, and the controller adds no console chatter to valid updates. It keeps collecting replies, including slow erase responses, without retrying them or imposing an update response deadline.

After an update, close the uploader and wait **10 seconds** before sending feed commands. `UPDATE_IDLE_TIMEOUT_MS` sets this gap. This blocks commands from the controller, not manual or external triggers on other feeders.

The uploader opens its port at 9600 baud. That host setting does not change the native USB transport or the feeder UART, which stays at `RS485_BAUD` (9600). You can also use a direct auto-direction USB-RS485 adapter.

## Change a feeder ID

The controller also forwards locally armed ID assignments. Select PA4 menu `01` on the feeder, close OpenPnP/serial monitors, then run from the feeder's `CODE_feeder` folder:

```sh
python tools/assign_id.py --port COM7 --address 7 --new-id 12
```

The PC tool checks responding destination IDs, targets the selected feeder's hardware UID, saves once and verifies at the new ID. See the [feeder button/wiring guide](../../V485-feeder/CODE_feeder/README.md#pa4-button-and-saved-settings). Manual PA4 menu `03` also changes an ID. Controller feeds remain blocked until assignment/update traffic has been idle for 10 seconds.

## Check without hardware

Run `python tools/check_bridge.py` with Python and a native `g++` compiler. It compiles the real controller code with simulated USB, UART and GPIO, then checks update packets, damaged or fragmented input, completion timing, lost/stale replies, faults and single-send behaviour. It opens no hardware ports. Build the ESP32 target separately with `pio run -e esp32c3`.
