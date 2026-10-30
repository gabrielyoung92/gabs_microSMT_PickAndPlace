# V485 firmware 0.1.3

Current application for the machine's 8/12/16/24 mm feeders. Original designs
and firmware: [MicroSMT](https://github.com/microsmt/Bing-feeder). Local changes
were prepared by Gab with ChatGPT assistance.

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

Universal application/loader builds and native C/protocol checks have passed.
Application 0.1.3 image CRC and startup inhibition have been verified on the
connected units. They remained idle and fault-free beyond the peel timeout.
Watchdog reset timing, loaded tape and pickup accuracy require bench tests.

See [operating/build instructions](README.md), [update protocol](BOOTLOADER.md)
and [dashboard](../USB_host/README.md).
