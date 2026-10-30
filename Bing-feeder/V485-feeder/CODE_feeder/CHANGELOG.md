# V485 firmware 0.1.4

Current application for the machine's 8/12/16/24 mm feeders. Original designs
and firmware: [MicroSMT](https://github.com/microsmt/Bing-feeder). Local changes
were prepared by Gab with ChatGPT assistance.

- Remaining quantity and completed advances live in feeder EEPROM, using twelve
  rotating CRC-checked records. Setting quantity resets advances; successful
  normal feeds save once. Polling never writes. Jogs and partial feeds do not
  deduct stock. Quantity supports 0–65,534 or Not set; advances saturate at the
  32-bit maximum. Host stock reads the feeder instead of estimating from pulses.
- Fault snapshots retain requested/received events, time and switch state.
  Holding/releasing PA4 for two seconds while faulted clears runtime errors with
  motors stopped, using the same guards as the bus clear command.
- Explicit tape-loading mode offers single-pocket feed/retract without stock
  deductions and peel-only take-up until tension, retaining the timeout.
- Known zero quantity alternates Lo with the idle ID. Unknown quantity and
  normal feeding remain unaffected. Configure exposes the existing Find command.
- HEALTH captures available reset flags. The installed loader clears these;
  the host reports unavailable rather than guessing. The loader stays unchanged.
- One universal image; each unit saves its ID, width, advance count, motor
  directions and tension-switch polarity.
- All widths start with peel take-up off until the first ordinary feed or
  feed-button press. Once armed, the switch controls take-up during feeds and
  while idle. Empty feeders do not raise E2 merely from booting. The ten-second
  continuous-run timeout remains active after arming.
- UID-addressed CLEAR clears runtime faults without rebooting, moving motors or
  changing saved settings. Invalid settings remain blocked.
- An independent hardware watchdog resets a stalled application after roughly
  four seconds; only main-loop progress refreshes it. The loader is unchanged.
- One best-effort CRC-checked startup ONLINE notification, staggered by ID.
  Regular status remains polled; missed notifications need no recovery.
- Latched motor-off input test exposes switch/button/optical states, switch
  changes, sensor total and uptime. Closing the web popup does not exit it.
- Addressed FEED/STATUS correlates completion and faults without replaying motion.
  DIAG/MONITOR expose heartbeat state and movement without EEPROM writes.
- Direct UID-targeted configuration, local button menus, item advance/retract,
  STOP and display/LED LOCATE remain available.
- Settings faults from an invalid options record can be repaired without a
  reboot. Motors remain inhibited through width/count/options saves until Clear
  Error; actual EEPROM write failures remain blocked.
- Normal application updates use the installed bootloader and preserve settings.
  Building automatically generates the dashboard's firmware bundle.

## Verification

Installed on 19 connected feeders on 31 October 2026. The 17,404-byte application
has CRC32 **BD526A6A**. Every unit reported the matching image, retained width
and advance count, readable stock and an idle, fault-free state beyond the peel
timeout. Motor-off input test, loading entry/exit and Find were checked through
the live host. The original bootloader remains unchanged.

Universal application/loader builds and native C/protocol checks pass. Checks
cover stock persistence/interrupted writes, counter limits, fault snapshots,
local clear, loading/peel timeout, host/API controls and UI state.

See [operating/build instructions](README.md), [update protocol](BOOTLOADER.md)
and [dashboard](../USB_host/README.md).
