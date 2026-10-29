# V485 firmware 0.1.2

Current application for the machine's 8/12/16/24 mm feeders. Original designs
and firmware: [MicroSMT](https://github.com/microsmt/Bing-feeder). Local changes
were prepared by Gab with ChatGPT assistance.

- One universal image; each unit saves its ID, width, advance count, motor
  directions and tension-switch polarity.
- On 8 mm feeders, peel take-up can finish after indexing stops. The tension
  switch ends that cycle; the ten-second peel timeout remains active.
- Latched motor-off input test exposes switch/button/optical states, switch
  changes, sensor total and uptime. Closing the web popup does not exit it.
- Addressed FEED/STATUS correlates completion and faults without replaying motion.
  DIAG/MONITOR expose heartbeat state and movement without EEPROM writes.
- Direct UID-targeted configuration, local button menus, item advance/retract,
  STOP and display/LED LOCATE remain available.
- Normal application updates use the installed bootloader and preserve settings.
  Building automatically generates the dashboard's firmware bundle.

## Verification

Universal application/loader builds and native C/protocol checks have passed.
Application 0.1.2 uploads have been CRC-verified on connected bench units. Loaded
tape movement, tension-switch mounting and pickup accuracy require bench tests.

See [operating/build instructions](README.md), [update protocol](BOOTLOADER.md)
and [dashboard](../USB_host/README.md).
