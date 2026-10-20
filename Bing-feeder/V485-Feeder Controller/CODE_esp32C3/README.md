# ESP32-C3 controller firmware

> **Original: [MicroSMT / Bing-feeder](https://github.com/microsmt/Bing-feeder).** [Credits and local changes](../../../CREDITS.md).

PlatformIO C++ adaptation of MicroSMT's V25 RS485 controller, version **0.1.0**, using the Arduino framework. The [changelog](CHANGELOG.md) records changes and build verification. **Hardware operation is untested.**

## Build

Open **this CODE_esp32C3 folder** in VS Code with PlatformIO. Select **Project Tasks → esp32c3 → Build**, or run:

```sh
pio run -e esp32c3
```

Edit [src/main.cpp](src/main.cpp) for firmware and [src/config.h](src/config.h) for GPIOs, baud rates, version and timing. Framework/USB settings are in [platformio.ini](platformio.ini). Outputs are in `.pio/build/esp32c3/`, ignored by Git.

## Board and connections

The supplied [module photo](esp32c3%20%20mini.bmp) shows an ESP32-C3 Super Mini. The project uses the `esp32-c3-devkitm-1` profile as a **4 MB C3 target**; confirm the actual module, pinout and flash size before uploading.

| Connection | Setting |
| --- | --- |
| USB console | Native USB CDC, 115200 baud, LF |
| RS485 UART0 RX / TX | GPIO20 / GPIO21, 9600 baud, 8N1 |
| RS485 direction | GPIO9, also BOOT |
| ACK / run indicators | GPIO7 / GPIO8 |

Native USB console flags keep UART0 free for RS485. Keep `monitor_speed` consistent with the console baud in `config.h`.

**MicroSMT advises powering the expansion board first:** otherwise its MAX3485 can prevent the C3 from starting. GPIO9 also controls boot mode, so retain the supplied wiring until the hardware is checked.

## Upload and monitor

With the board ready, use PlatformIO's Upload/Monitor tasks or:

```sh
pio run -e esp32c3 -t upload --upload-port COM7
pio device monitor -e esp32c3 --port COM7
```

Replace COM7 with the actual port. If download mode does not start automatically, hold BOOT, press/release RESET, release BOOT and retry.

## Feed commands

Send `M600 N12 F4` or `N12 F4` followed by LF. N/F values are 0–99, in that order; letter case, spaces/tabs and CRLF are accepted. Malformed values and extra fields are rejected.

Each feed command is sent **once**. `OK` means accepted, `BUSY` means rejected, and a missing/invalid reply leaves the outcome **unknown**. Do not blindly resend after a timeout: the tape may already have moved. The protocol has no reply address or transaction ID and does not confirm feed completion.

Input is limited to 32 bytes before LF, with a one-second inter-byte timeout. Replies must be complete, within 16 bytes, and arrive within the configured 300 ms ACK window.

This controller does not forward firmware-update packets. Use a direct USB-RS485 adapter for [feeder updates](../../V485-feeder/CODE_feeder/BOOTLOADER.md).
