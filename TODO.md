# Remaining machine work

The [dashboard](Bing-feeder/V485-feeder/USB_host/README.md) and
[firmware 0.1.4](Bing-feeder/V485-feeder/CODE_feeder/README.md) are implemented.
Motion, cameras, pickup teaching, nozzle management and jobs stay in OpenPnP.

- [ ] Check switch-controlled peel take-up on loaded tape for each width,
  including startup inhibition, first-feed arming and stopping at tension.
- [ ] Bench-check watchdog recovery and Clear error without unexpected movement.
- [ ] Check the motor-off input popup against the physical switch, buttons and
  optical sensor on the units in use.
- [ ] Verify feed distance, motor directions and saved stock counts against tape use.
- [ ] Add, teach and enable a powered feeder in OpenPnP; complete a feed/pick trial.
- [ ] Teach nozzle changer positions and test N1/N2 loading and unloading.
- [ ] Finish camera, nozzle-offset, vacuum and placement calibration.

Keep host addresses, credentials, machine profiles, stock and build outputs out
of the public repository.
