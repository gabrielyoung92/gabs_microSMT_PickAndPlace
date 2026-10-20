# Machine setup status

Updated 2026-10-14. The machine remains under assembly. OpenPnP is operational
on the Raspberry Pi 5; the owner deferred calibration until mechanical work is
complete. Retain the stock LPC1769 Smoothieware PnP motion system.

## Host and OpenPnP

ARM64 Raspberry Pi OS desktop / Debian 13, OpenPnP 2.6 and OpenJDK 21 desktop
runtime installed. SSH and headless WayVNC desktop work; desktop output is
1920×1080 at scale 1.0. VNC uses Linux account authentication. Password reset
resolved the observed authentication failure; credentials are not recorded.

One serial motion driver, two cameras, two nozzle valves, pump and two camera
lights configured. [Reviewed command blocks](openpnp-gcode.md) include comments,
consistent controller/OpenPnP speeds and the physical output mappings. Initial
configuration and pre-review configuration were backed up locally.

Automatic home on enable is explicitly selected. Current `G28` searches X/Y
together and then Z using stock firmware behavior. The initial separate-axis
slow test sequence has been superseded. Stock fast rates X50/Y40/Z50 mm/s and
25 mm/s second-pass rates remain unchanged. No G0 Z0 precedes homing.
The central Z gate requires heads level or N2 below N1 at the start. Recovery
from the other side has not been resolved.

Operating limits are XY 200 mm/s, Z 50 mm/s, rotations 360°/s; acceleration
XY 1000 mm/s², Z 500 mm/s², rotations 2000°/s². Owner reports homing still feels
slow but acceptable, and revised motion speed feels good so far. This is an
operational observation, not a repeatability or maximum-performance measurement.

## Evidence completed

- Stock firmware identity verified: LPC1769, feature/best-for-pnp-23a1f0db.
- All five motor channels have owner-observed motion. Earlier owner measurements
  verified X/Y 300 mm travel and Z 10 mm per head with opposite directions.
- Homing on the Pi completed; all XYZ endstops triggered and controller reported
  Idle at XYZ=0. Owner subsequently confirmed OpenPnP operation and homing.
- Top `1e45:8023` and bottom `1e46:8024` USB cameras enumerated. Both report serial
  HB2025070001; distinct product identities and persistent paths separate them.
- Both cameras streamed concurrently: 150 frames each over five seconds at
  1080p MJPEG. OpenPnP's capture backend returned 1920×1080 images from both.
- Bottom LED M804/M805 and top LED M806/M807 physically identified by owner.
- Pump operation heard by owner. Configured N1 command operates the intended
  valve; incorrect pneumatic tubing was found. Corrected routing and nozzle
  suction/release are not yet documented as verified. N2 physical test pending.
- Original SD files retained. Saved travel-limit values returned by SD queries
  after a power cycle; loaded runtime enforcement is still not proven.
- OpenPnP XML loader, command comment stripping, variable substitutions, output
  command mappings and response regexes validated without commanding motion.

## Current boundaries

XYZ raw bounds: X 0–385 mm, Y 0–470 mm, Z −30–+30 mm. Steps/mm remain unchanged.
N1 uses raw Z, N2 uses negated mapped Z. Rotation angle calibration remains open.
G92 A0 B0 assigns current angular zero without physical rotary homing.

Supplied camera scales, nozzle offsets and bottom-camera location are retained
as estimates. Camera distortion calibration, nozzle runout recalibration and
automatic nozzle changing are disabled. Sample feeders and absent Mega feeder
drivers removed. No real placement job or full machine calibration performed.
Current camera IDs include USB port topology; reselect if camera ports change.
Camera lights are configured for initial manual control.

The last direct pump/N1 session ended with acknowledged valve/pump off commands.
Later OpenPnP use can change output/motor state; inspect current state next time.
Never infer current physical position from historical coordinates after a move,
power cycle or manual movement. Back up and edit XML only with OpenPnP closed.

## Next work when assembly is ready

- Verify tubing, independently test N1/N2 suction and release, and confirm pump off.
- Install two [XGZP6847A100KPGN33 sensors with an ESP32-C3](vacuum-sensors.md).
  No pump sensor planned. Identify board and verify input circuitry before build.
- Focus/orient both cameras and calibrate scale at working heights.
- Calibrate nozzle XY offsets, bottom-camera location, Z heights and clearance
  for both coupled heads, rotation angle and runout.
- Validate software limits, emergency-stop function and loaded motion repeatability.
- Establish nozzle tips and feeder configurations before a placement trial.

Raw Pi-session evidence and configuration backups remain in ignored local
material. The earlier [controller inspection](../hardware/CONTROLLER_INSPECTION.md)
retains the measurement history; [hardware inventory](../hardware/MACHINE_HARDWARE.md)
records devices. No motion-controller firmware was flashed in this setup.
