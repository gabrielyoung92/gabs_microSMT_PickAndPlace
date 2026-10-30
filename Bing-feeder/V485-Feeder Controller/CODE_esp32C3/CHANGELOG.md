# ESP32-C3 bridge 0.1.0

MicroSMT-derived RS485 controller using PlatformIO/Arduino. This machine uses the
[direct PC host](../../V485-feeder/USB_host/README.md); this source supports the
separate controller board.

- USB accepts `M600 N… F…` or `N… F…`. IDs are 1–99; F counts sensor events,
  and F0 selects the feeder's saved count.
- Sends FEED once, polls matching STATUS and returns `ok` only after DONE.
  Busy, fault, unknown outcome and timeout return errors without replaying motion.
- RS485 runs at 115200 baud. CRC-checked application-update and settings packets
  pass through unchanged; the PC uploader handles retries and verification.
- Feeds are blocked until update/settings traffic has been idle for ten seconds.
- Bounded USB/UART parsing rejects malformed and overlong packets.

PlatformIO and native controller/feeder checks have passed, including lost/stale
replies, faults, timeouts, fragmentation, CRC and single-send movement. See
[build and wiring instructions](README.md). Original firmware and hardware:
[MicroSMT](https://github.com/microsmt/Bing-feeder); local changes by Gab with
ChatGPT assistance.
