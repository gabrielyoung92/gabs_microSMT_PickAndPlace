# Machine software TODO

## Implemented

- [x] Powered-feeder dashboard on port 80; one direct USB–RS485 owner and local
  feeder TCP bridge for OpenPnP. Smoothieboard and cameras stay in OpenPnP.
- [x] Compact overview with ID, width, spacing, online/offline state, errors,
  firmware and stock; configuration and reel editing in popovers.
- [x] Fair discovery, regular DIAG polling and details refreshed on discovery,
  reconnect, reboot or host startup. Pausing commands keeps telemetry running.
- [x] Firmware 0.1.2, automatic build bundle and Current/Update available/Unknown
  indication. One server queue for single/bulk updates, per-unit progress,
  CRC verification and explicit retry after failure. Existing bootloader retained.
- [x] 8 mm peel cycle can finish after indexing; tension switch stops it and
  the independent ten-second timeout remains.
- [x] Motor-off input test for switch, buttons and optical sensor, with explicit exit.
- [x] Feeder directions, switch polarity and advance spacing with verified saves.
- [x] Sensor-based reel stock by hardware UID, part selection and automatic
  creation of a missing disabled powered feeder in OpenPnP.
- [x] Compact native part/package creation/editing, footprint preview and package
  tip selection; physical nozzle management stays in OpenPnP.
- [x] Remaining-job stock check: Part, Need, Stock, Result. Jobs run in OpenPnP.
- [x] Separate page URLs; no web motion, camera streaming, nozzle management,
  backup/restore or strip/tray setup.

## Bench checks remaining

- [ ] Test the 0.1.2 peel cycle with loaded tape and verify the tension switch
  stops take-up after the index motor stops.
- [ ] Exercise the motor-off input popup on physical units; confirm contact
  changes and both button/sensor readings match the mechanism.
- [ ] Verify configured advance distance, feed/peel directions and stock estimates
  against actual tape movement on the widths in use.
- [ ] Add/teach/enable a powered feeder in OpenPnP and complete a feed/pick trial.
- [ ] Finish nozzle changer positions and physical load/unload tests in OpenPnP.
- [ ] Complete camera, nozzle-offset, vacuum and placement calibration on the machine.

## Repository

- [x] Document the current firmware, host and OpenPnP boundary.
- [x] Review source/documentation and exclude private machine data before publication.

Keep host addresses, credentials, SSH keys, machine profiles, inventory and
build outputs out of the public repository.
