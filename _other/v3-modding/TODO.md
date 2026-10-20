# Next work

## Established

- [x] Create the project; consolidate vendor sources in the `../../Bing-feeder/` and `../../Microsmt-PNPv3/` source directories.
- [x] Locate individual feeder C source, schematic, Mega source and V3.1 binary.
- [x] Record the V2 schematic / V3 packaging uncertainty and preliminary pin map.
- [x] Start a portable feed-cycle core with host behavior tests.

## Machine setup on Raspberry Pi

- [x] Verify headless 1080p VNC desktop and install OpenPnP 2.6 / Java 21.
- [x] Adapt machine configuration for Linux serial and both cameras.
- [x] Validate camera capture and identify top/bottom lighting commands.
- [x] Enable automatic homing and review/comment all G-code command blocks.
- [x] Receive owner confirmation of OpenPnP homing and revised motion operation.
- [ ] Finish mechanical assembly; calibration is deferred until then.
- [ ] Retest corrected N1 tubing, test N2 suction/release and confirm pump stop.
- [ ] Calibrate cameras, nozzle offsets, working/clearance Z, rotation and runout.
- [ ] Validate runtime travel limits and physical emergency-stop operation.

See [current setup status](docs/machine-setup-status.md).

## Hardware reconstruction

- [x] Recover native KiCad schematics, PCBs and projects for the feeder and all
      three busbar archives, with portable project libraries.
- [x] Match schematic/PCB pad nets and compare exported copper with source CAM.
- [ ] Resolve the apparent N1-N8 / N9-N16 archive duplication with upstream.
- [ ] Confirm regulator tab, MCU identity, switch pad functions and actual
      connector part numbers/numbering against physical hardware.
- [ ] Create a separately reviewed redesign from the recovered reference; replace
      traced pour contours, define real courtyards/stackup and resolve DRC findings.

## Motherboard expansion

- [x] Recover the supplied four-layer LPC1769 motherboard as a linked native
      KiCad PCB and hierarchical schematic with source/CAM validation.
- [x] Inventory all MCU pins; reserve UART RX/TX and three analog vacuum inputs
      (P0.23 / AD0.0 and P0.24 / AD0.1 for heads; P1.30 / AD0.4 for pump/manifold).
- [ ] Verify the delivered motherboard, exact PnP firmware and configuration.
- [ ] Audit P2.11 feeder-bus candidate pin mux, timer/interrupt ownership and
      practical attachment before porting the controller into a Smoothieware module.
- [x] Select CFSensor XGZP6847A100KPGN33 vacuum sensors; current scope is N1/N2 only.
- [x] Select two nozzle sensors on a separate ESP32-C3 USB board; omit the pump sensor.
- [ ] Verify the C3 board, two ADC1 divider/filter circuits, firmware reporting and
      OpenPnP integration; calibrate both channels. See [sensor plan](docs/vacuum-sensors.md).

## Next firmware investigation

- [ ] Confirm the target feeder PCB revision and full MCU marking. Obtain the
      matching source/build project, programming instructions and bootloader details.
- [ ] Check whether the published C source actually builds the supplied V3.1 HEX.
      Locate or reconstruct the startup, linker, clock and library configuration.
- [ ] Trace current V3 contact/backplane routing, PA5 and PA11 availability,
      optical signal levels and power behavior against the supplied V2 schematic.
- [x] Inspect OpenPnP Photon packet/actuator transport; keep the diagnostic bench
      protocol explicitly separate from future OpenPnP integration.
- [x] Build CMSIS-only STM32 candidate firmware and Pico SDK USB bridge images
      for Pico 2 and Pico 2 W in PlatformIO; add VS Code setup and host tests.
- [x] Implement bounded diagnostic exchanges with CRC, correlation and observable
      transport faults; keep all feeder motor commands inhibited.
- [x] Add a shared Pico controller command engine, bounded UID scan/cancel and
      optional Pico 2 W Wi-Fi TCP diagnostics; test callbacks with SDK fakes.
- [ ] Validate Pico 2 W bus timing under actual radio/TCP load; select PIO or
      a dedicated timing core if the software sampler cannot meet deadlines.
- [ ] Choose bus circuitry and slot-ID connection; extend diagnostic framing/CRC
      with motion sessions, replay protection, timeouts and fault recovery.
- [ ] Add a timer-based sensor qualifier and board adapter after establishing
      motor polarity, braking, peel-motor sequencing and indexing geometry.

## Hardware validation

- [ ] Record the actual board identity and stock firmware/recovery procedure.
- [ ] Assemble/calibrate/prove the stock machine and feeders.
- [ ] Measure sensor edges, stock indexing timing, voltages and contact behavior.
- [ ] Test an isolated prototype, then two nodes and the populated feeder bank.

## Before distribution

- [ ] Select a license for new work and clarify MicroSMT PNPv3 material's terms.
- [ ] Review contents and commit metadata for private information. Repository
      visibility changes require the owner's explicit request.
