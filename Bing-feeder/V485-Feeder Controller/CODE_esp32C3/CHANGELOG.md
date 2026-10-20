# ESP32-C3 controller changelog

Original firmware: [MicroSMT / Bing-feeder](https://github.com/microsmt/Bing-feeder), ESP32-C3 RS485 master V25. Changes here are local adaptations made with ChatGPT assistance. The versions below identify this local firmware, not an official MicroSMT release.

## 0.1.0 — 2026-10-20

- Converted the Arduino sketch to a PlatformIO project with `src/main.cpp` and `src/config.h`; removed the `.ino` and merged the supplied text README's module notes into `README.md`.
- Added `FIRMWARE_VERSION` in `config.h` and printed the version and MicroSMT V25 origin at startup.
- Retained the original GPIOs, RS485/USB baud settings and LED timing defaults. Enabled the native USB console so UART0 remains available for RS485.
- Replaced permissive command parsing with exact `N0..99 F0..99` commands, optionally prefixed by `M600`. Letter case and surrounding spaces/tabs/CR are accepted; malformed values, duplicates, unknown commands and extra tokens are rejected.
- Replaced blocking, unbounded USB reads with a bounded line buffer. A complete LF-terminated line is required. Overflow, embedded NUL and inter-byte timeout discard the entire line through the next LF.
- Removed automatic motion-command retries. A lost ACK leaves the outcome unknown, so sending the same command again could advance the tape twice.
- Required complete, bounded ACK lines. Missing newlines, overflow and embedded NUL no longer allow a truncated `OK` prefix to pass.
- Kept `BUSY`, timeout and invalid-response results distinct. Changed success text to report command acceptance rather than verified movement.
- Removed the incorrect `flush()` explanation and extra frame-length delay. The pinned Arduino core waits for TX to become idle; the controller then releases the RS485 transmitter for replies.
- Removed per-command UART teardown/reinitialisation; discard queued RX bytes before each transmission instead.
- Corrected two-flash LED sequencing and updated comments to describe configurable settings and protocol limits.
- Removed the development test folder at the owner's request.

Built on 20 October 2026 with Espressif32 7.1.3 and Arduino framework package `4.20017.260907+sha.dcc1105b`; the build and software checks passed. This version has not been flashed or physically validated. The supplied protocol still has bare `OK`/`BUSY` replies without transaction IDs; late replies and physical feed completion cannot be proven from those replies alone.
