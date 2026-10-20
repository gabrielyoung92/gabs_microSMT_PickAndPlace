# ESP32-C3 controller firmware

> **Original source: [MicroSMT / Bing-feeder](https://github.com/microsmt/Bing-feeder).** This is Gab's independently reorganised copy, prepared with help from ChatGPT. The original MicroSMT designs remain credited to their authors. [Credits and changes](../../../CREDITS.md).

PlatformIO C++ project adapted from MicroSMT's V25 ESP32-C3 RS485 controller sketch by Gab with ChatGPT assistance. Local firmware version **0.1.0** adds stricter input/ACK handling and single-shot transmissions; it is not an official MicroSMT release. The firmware is [src/main.cpp](src/main.cpp), using the Arduino framework, with its version, hardware and timing settings in [src/config.h](src/config.h). See the [changelog](CHANGELOG.md) for changes from the supplied sketch.

| Browse | Contents |
| --- | --- |
| [Active C++ source](src/main.cpp) | Edit this file for PlatformIO firmware changes |
| [Hardware configuration](src/config.h) | Version, GPIOs, UART, baud rates, LED timing and input/ACK timeouts |
| [PlatformIO project](platformio.ini) | Board, Arduino framework, USB and serial settings |
| [Changelog](CHANGELOG.md) | Local firmware versions and changes |
| [Controller collection](../README.md) | PCB files and busbars |

## Build in VS Code

1. Install the **PlatformIO IDE** extension in VS Code.
2. In PlatformIO Home, choose **Open Project** and select this `CODE_esp32C3` folder, which contains `platformio.ini`.
3. Under **Project Tasks → esp32c3 → General**, select **Build**.

Alternatively, from a PlatformIO terminal in this folder:

```sh
pio run -e esp32c3
```

PlatformIO installs the required compiler and Arduino framework on the first build. No extra libraries are needed. It compiles `src/main.cpp` and includes `config.h` from the same `src/` directory. Build output is in `.pio/build/esp32c3/` and is ignored by Git.

**Version 0.1.0 build verified on 20 October 2026:** Espressif32 platform 7.1.3, Arduino framework package `4.20017.260907+sha.dcc1105b`. The compiler, linker and image generation passed. Hardware operation remains untested.

## Board and USB configuration

Edit **`src/config.h`** for `FIRMWARE_VERSION`, GPIO assignments, the RS485 UART and baud rate, USB console baud setting, LED intervals, input limits and timeouts. Keep `monitor_speed` in `platformio.ini` consistent with the console setting. USB framework flags and the board profile stay in `platformio.ini` because they apply to the framework build as well as `main.cpp`.

The supplied [module image](esp32c3%20%20mini.bmp) shows an ESP32-C3 Super Mini. The project uses PlatformIO's `esp32-c3-devkitm-1` profile as a **4 MB ESP32-C3 build target**, with the sketch's explicit GPIO numbers. This profile is not a claim that the supplied module is an Espressif DevKitM board; confirm the actual module and flash size before uploading.

`ARDUINO_USB_MODE=1` and `ARDUINO_USB_CDC_ON_BOOT=1` route the sketch's `Serial` console through native USB. This matters because the sketch separately uses UART0 for RS485; routing the console to UART0 would conflict with the feeder connection.

| Connection | Configuration retained from the sketch |
| --- | --- |
| USB command console | Native USB CDC, 115200 monitor setting, LF line endings |
| RS485 UART0 RX / TX | GPIO20 / GPIO21, 9600 baud, 8N1 |
| RS485 direction | GPIO9 |
| ACK indicator / run indicator | GPIO7 / GPIO8 |

MicroSMT's supplied notes say to use a module matching the photo's size and pinout, and to power the expansion board first: otherwise its MAX3485 can hold a level low and prevent the ESP32-C3 from starting. These notes are retained here instead of a separate text README. GPIO9 is also the module's BOOT pin, so board power and the RS485 direction circuit matter when entering the bootloader. Keep the original pin assignments until the actual controller wiring has been checked.

## Upload and monitor

Once the board and connected hardware are ready, PlatformIO's **Upload** task uses the selected USB port. The equivalent terminal commands are:

```sh
pio run -e esp32c3 -t upload
pio device monitor -e esp32c3
```

For multiple connected boards, add `--upload-port COM7` to the upload command and `--port COM7` to the monitor command, replacing `COM7` with the actual Windows port. If the module does not enter download mode automatically, hold **BOOT**, press and release **RESET**, then release **BOOT** and retry Upload.

## Commands and responses

Send `M600 N12 F4` or `N12 F4` followed by LF. `N` and `F` must appear in that order, with values from 0 through 99. Letter case, spaces/tabs and CRLF are accepted. Unknown command prefixes, duplicate fields, negative/oversized values and extra tokens are rejected.

The input limit is 32 bytes before LF. A partial line that waits 1,000 ms between reads, an overlong line or embedded NUL is rejected; input is discarded through the next LF before another command can be accepted. USB line collection does not block the LED handlers. The controller waits up to 300 ms for an ACK after sending a command.

Each movement command is transmitted **once**. `OK` means the feeder acknowledged acceptance, `BUSY` means it did not accept this command, and a missing/invalid ACK means the outcome is **unknown**. Do not blindly resend after a timeout: the first command may already have moved the tape. A reply is limited to 16 bytes before LF and must be complete. No physical movement or completion is verified by the host.

The supplied protocol has no reply address or transaction ID. Clearing queued RX data does not prove that a later reply belongs to the current command. No hardware has been flashed or physically tested for this version.

## Configuration references

- [PlatformIO ESP32-C3-DevKitM-1 board profile](https://docs.platformio.org/en/latest/boards/espressif32/esp32-c3-devkitm-1.html)
- [Espressif USB CDC configuration](https://docs.espressif.com/projects/arduino-esp32/en/latest/guides/tools_menu.html#usb-cdc-on-boot)
