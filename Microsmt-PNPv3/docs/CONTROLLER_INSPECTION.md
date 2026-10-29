# Delivered controller inspection

Current continuation: [Machine/OpenPnP setup](machine-setup-status.md)
records later homing, camera/output tests and the revised operating profile.
The dated sections below preserve the earlier measurement chronology.

2026-10-14 (Australia/Brisbane). Initially USB only, with no other connections
and no 24 V according to the owner. During inspection the owner connected 24 V;
the controller continued to respond and report Idle. Supply voltage, polarity,
driver supply rails and other connections were not physically measured.
The initial inspection used only identity and status queries. Subsequently,
the owner connected all five motors and three endstops and confirmed readiness
for bounded individual motor tests, then explicitly requested XYZ homing.
No auxiliary output commands, resets, flashing or persistent configuration
writes were performed.

## Identity and communication

| Property | Observed value |
| --- | --- |
| USB manufacturer / product | `Uberclock` / `Smoothieboard` |
| USB VID:PID | `1d50:6015` |
| USB serial | `1400901695CA84E3619F5D00F50020C4` |
| Serial interface | `cdc_acm`, `/dev/ttyACM0` at inspection |
| Persistent serial path | `/dev/serial/by-id/usb-Uberclock_Smoothieboard_1400901695CA84E3619F5D00F50020C4-if00` |
| Successful session | 115200 baud, 8N1, no flow control, DTR/RTS deasserted |
| Firmware-reported MCU / clock | LPC1769 / 120 MHz |
| Running build | `feature/best-for-pnp-23a1f0db` |
| Firmware build date | `Feb 15 2021 20:34:17` |
| Firmware-reported source | `https://github.com/markmaker/Smoothieware/tree/feature/best-for-pnp` |
| Axes / physical axes | 5 / 5: X, Y, Z, A, B |
| Firmware flags | GRBL mode 0, CNC 0, mass storage 1 |
| Shipped manual title | `Microsmt pnpboard v1.7 (2023/06/01)`; not a physical PCB revision verification |

Queries: `version`, `M115`, `M114`, `M119`, `mem`, `help`, `get state`,
`get status`, `M503`. Read-only command references:
[Smoothieware console commands](https://smoothieware.org/console-commands) and
[supported G codes](https://smoothieware.org/supported-g-codes.html).

## Live status

- USB-only and after owner-reported 24 V connection: `Idle`.
- Reported positions: X/Y/Z/A/B all zero; these are controller coordinates,
  not evidence of homing or physical position.
- Endstops: `X_min:1 Y_min:1 Z_min:1`, at P1.24/P1.26/P1.28. This is consistent
  with disconnected active-high inputs, not a functional endstop test.
- Initial modal state: millimetres, absolute coordinates, G54, feed 5000.
- `M503`: no configuration override; steps and acceleration agree with SD
  configuration. Live Z actuator rate is 595 units/s, despite the SD setting
  of 200000 units/min; do not assume every configured rate is applied unchanged.
- Memory query: total free RAM 5556 bytes; AHB0 free 9736 and AHB1 free 10440.

Raw [initial serial transcript](evidence/controller-2026-10-14/serial-inspection.txt)
and [24 V status transcript](evidence/controller-2026-10-14/serial-24v-inspection.txt).

## SD preservation

The host exposed `/dev/sdb1`, FAT, on a 481 MiB `MBED USB DISK`.
It was mounted read-only with `nosuid,nodev,noexec`, copied, verified byte for
byte (19 files, 1410020 bytes), then unmounted. The complete file backup and
SHA-256 manifest are in ignored local material under
the repository-root `.local/v3-modding/controller-2026-10-14/`. This is a file backup, not a full disk image
or a tested bootloader recovery procedure.

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `FIRMWARE.CUR` | 388208 | `8fd0b46be73577ffc89cd8588e6c7bc0932d91d2e4959124779d60b8ae3b6dcf` |
| `config.txt` | 20443 | `ae0c257f09de19d43a587d47b40fceda45e6b80f8599e647f678a097027519b3` |

Root firmware and config are byte-identical to those in
`backup20250726-1080-T&B/`. `FIRMWARE.CUR` is the SD firmware artifact;
MCU flash was not read back. The card also holds OpenPnP XML configuration,
the board manual and a motor direction PDF. Existing XML includes Windows
COM ports and a homing sequence beginning with `G0 Z0`, then `G28`;
it needs review before use on this machine.

## Shipped motion and output configuration

The preserved [SD config](evidence/controller-2026-10-14/config.txt) specifies:

| Axis | Steps per unit | STEP | DIR | ENABLE | Configured max rate per minute | Axis acceleration |
| --- | --- | --- | --- | --- | --- | --- |
| X | 80 | P2.0 | P0.5 inverted | P0.4 | 60000 | 6000 |
| Y | 80 | P2.1 | P0.11 inverted | P0.10 | 48000 | 3000 |
| Z | 168 | P2.2 | P0.20 inverted | P0.19 | 200000 | 15000 |
| A / N1 | 17.7777 | P2.3 | P0.22 | P0.21 | 200000 | 10000 |
| B / N2 | 17.7777 | P2.8 | P2.13 | P4.29 | 200000 | 10000 |

XYZ units are mm; A/N1 is annotated steps per degree. B/N2 is a nozzle rotation
channel, but its config comments incorrectly describe mm. Mechanical scaling
and direction are unverified. Global acceleration is 10000; default feed/seek
5000 per minute. These are stock settings, not selected bench-test rates.

Minimum XYZ homing inputs are enabled; maximum inputs and hard limits are
disabled. Fast/slow homing rates are X 50/25, Y 40/25, Z 50/25 mm/s.
The kill input is enabled on P2.12 with toggle mode; no switch function has
been demonstrated.

| Configured output | On / off commands | Pin |
| --- | --- | --- |
| N1 vacuum | M800 / M801 | P2.7 |
| N2 vacuum | M802 / M803 | P2.5 |
| Up camera lights | M804 / M805 | P2.4 |
| Down camera lights | M806 / M807 | P1.22 |
| Vacuum pump | M808 / M809 | P1.23 |
| Drag | M810 / M811 | P2.6 |

All listed outputs remain untested. Motor current entries in the config are
commented out. The shipped manual describes TMC2209 modules and physical Vref
adjustment under 24 V, with factory 32 microsteps; actual installed modules,
current settings and microstep jumpers need confirmation.

## Before the first motor test

Confirm the selected motor/channel, coil-pair wiring, installed driver and
current setting. Disconnect motor wiring only with power removed. Use a
bounded low-speed single-axis test after the owner confirms its connections
and mechanical clearance; homing requires functional endstops first.
USB responses alone do not validate the 24 V driver power path or motor outputs.

## Initial motor and endstop tests

The owner confirmed axis clearance, driver current settings and access to a
stop/power switch before movement. With the endstops connected, X/Y read zero
and Z read one. After the owner moved the head, all three read zero. This
establishes a change on the Z input; individual X/Y switch actuation remains
to be demonstrated.

X tests used 1 mm out/back at 1 mm/s, then 10 mm forward at 2 mm/s and 10 mm
back at 10 mm/s, with temporarily reduced X acceleration. The owner confirmed
visible left/right movement of the head gantry after the faster test.
Controller coordinates returned to X=0 and Idle, with X acceleration restored
to 6000 and absolute positioning restored. This confirms owner-observed X
motion, not calibrated travel, homing or full-speed performance.

Y was commanded 10 mm out/back at 10 mm/s, with acceleration temporarily set
to 50. The owner confirmed visible forward/back movement. Controller
coordinates returned to Y=0 and Idle, with Y acceleration restored to 3000
and absolute positioning restored. Travel and direction remain uncalibrated.

Z was commanded 2 mm out/back at 2 mm/s, with acceleration temporarily set
to 20. The owner confirmed head movement and identified the mechanism:
one Z motor drives both heads through a shared belt. Controller coordinates
returned to Z=0 and Idle, with Z acceleration restored to 15000 and absolute
positioning restored. Measured displacement and belt geometry remain unverified.

N1/A was commanded 15 configured degrees out/back at 10 degrees/s, with
acceleration temporarily set to 50. The owner confirmed N1 movement.
Controller coordinates returned to A=0 and Idle, with A acceleration restored
to 10000 and absolute positioning restored. Rotation angle remains unmeasured.

N2/B was commanded 15 configured degrees out/back at 10 degrees/s, with
acceleration temporarily set to 50. The owner confirmed N2 movement.
Controller coordinates returned to B=0 and Idle, with B acceleration restored
to 10000 and absolute positioning restored. Rotation angle remains unmeasured.

The owner held the X endstop switch: `M119` reported `X_min:1 Y_min:0 Z_min:0`,
confirming X changed from its previously released zero reading without changing
the Y/Z inputs. With X released and Y held, `M119` reported
`X_min:0 Y_min:1 Z_min:0`, confirming X release and the Y trigger transition.
Y release back to zero remains to be checked.

All five motor channels now have owner-observed movement. Complete endstop
release checks, emergency stop function, calibrated travel/rotation, loaded
operation and full-speed operation remain unverified.

## First homing test

The owner identified X home as all the way left and Y home as all the way
front, and explicitly authorized Z homing before final gate adjustment.
The matching upstream `23a1f0db` Endstops and Robot source was inspected to
confirm individual-axis `G28` handling and actuator speed limiting.

Commands were `G28 Z`, then `G28 X`, then `G28 Y`. Temporary Cartesian and
actuator speed caps were X/Y 10 mm/s and Z 2 mm/s, with XYZ acceleration
set to 20. Each homing command completed with an acknowledgement and Idle
status. The final readings were `X_min:1 Y_min:1 Z_min:1` and X/Y/Z=0.
The owner confirmed that the machine had homed and reported that the first
run was slow.

Original Cartesian limits (X 1000, Y 800, Z 3333.33325 units/s), actuator
limits (X 1000, Y 800, Z 595 units/s), and XYZ acceleration (6000/3000/15000)
were restored after success. No settings were saved to SD. Stock homing rates
remain X 50/25, Y 40/25 and Z 50/25 mm/s; faster homing remains untested.
Final status was Idle. Z gate alignment and head levelling remain mechanical
adjustments; this test does not establish calibrated Z reference geometry.

Raw [first homing transcript](evidence/controller-2026-10-14/first-homing.txt).

## X travel calibration

After homing, the owner requested a +300 mm X move for measurement. The move
used the unchanged 80 steps/mm setting, commanded speed 25 mm/s and temporary
X acceleration 100. The controller completed the move and reported Idle at
X=300, Y/Z/A/B=0; X endstop released to zero. X acceleration was restored to
6000 and absolute positioning restored. The owner lost the reference mark,
so X was subsequently returned to zero at 25 mm/s for a new mark. The return
completed with Idle status and X endstop triggered. Actual displacement is
pending owner measurement; steps/mm remain unchanged. After the owner made a
new mark, X was commanded from zero to 300 at 100 mm/s, with temporary
acceleration 500. The controller completed the move and reported Idle at
X=300; acceleration was restored to 6000. The owner measured 300 mm actual
travel for the 300 mm command. X remains at 80 steps/mm unchanged; accuracy
beyond the owner's measurement resolution and repeatability are unverified.

Raw [300 mm calibration command transcript](evidence/controller-2026-10-14/x-calibration-300mm.txt).

## Y travel calibration

The owner requested Y=300 from home at 100 mm/s. Using the unchanged
80 steps/mm setting and temporary Y acceleration 500, the controller
completed the move and reported Idle at X=300, Y=300, Z/A/B=0. Y acceleration
was restored to 3000; Y was left at 300 for measurement. The owner confirmed
300 mm actual travel. Y remains at 80 steps/mm unchanged; accuracy beyond
the owner's measurement resolution and repeatability are unverified.

Y was subsequently returned to zero at 100 mm/s, with Y acceleration restored
to 3000. The controller reported Idle at X=300, Y=0, Z=0.

Raw [Y calibration transcript](evidence/controller-2026-10-14/y-calibration-300mm-100mms.txt).

## Z travel calibration

After the owner confirmed measurement setup and clearance for both heads,
Z was commanded from zero to 10 mm at 5 mm/s with temporary acceleration 50.
The unchanged Z setting is 168 steps/mm. The controller completed the move
and reported Idle at X=300, Y=0, Z=10; Z endstop released to zero. Z acceleration
was restored to 15000, with absolute positioning retained. The heads remain
at Z=10. The owner measured N2 10 mm below its Z=0 height and N1 10 mm
above its Z=0 height, giving 20 mm height difference between the heads.
The shared belt drives the two heads in opposite vertical directions:
positive Z lowers N2 and raises N1. Both were reported at equal height at home.
Keep Z at 168 steps/mm unchanged; accuracy beyond the owner's measurement
resolution and repeatability are unverified. OpenPnP nozzle Z mapping must
account for the opposite directions.

Raw [Z calibration transcript](evidence/controller-2026-10-14/z-calibration-10mm.txt).

## Manual travel measurement

The owner replaced the next homing request with a request to disable all
motors for manual measurement. `M84` was acknowledged and the controller
reported Idle at its retained coordinates X=300, Y=0, Z=10. No further homing
was sent. These coordinates cease to describe physical position after manual
axis movement; rehome before subsequent commanded positioning.

Raw [motor disable transcript](evidence/controller-2026-10-14/motors-disabled.txt).

## Owner measured travel limits

The owner measured maximum X travel 385 mm and Y travel 470 mm by hand with
motors disabled. Absolute Z travel was reported as 62 mm head-to-head height
difference; the selected usable difference is 60 mm. With the heads level at
Z=0, use Z −30 to +30 mm: at either endpoint one head is 30 mm up and the
other is 30 mm down. These are owner measurements, not controller-derived
physical travel measurements.

Saved software limits: X 0–385, Y 0–470, Z −30–+30 mm, enabled with halt
on an out-of-bounds command. Limits apply only after the corresponding axis
is homed. They are independent of homing search distances and steps/mm.
The original SD configuration is preserved in the initial local backup.
The new SD config was read-back verified with SHA-256
`dc4281f0544bff556dff40915cab60cf8921cc62f13bc28a62a5661d13c392c5`.
Restart/loading and runtime limit validation are pending; limits are not yet
confirmed active.

### Centre Z homing concern

After manual measurement, the owner reported N2 above N1, placing Z on the
negative side of the level-head reference. Stock Z homing always searches in
the negative direction, so from this position it would move away from the
centre gate toward the mechanical stop. No further homing or restart was sent.
Software limits do not solve this: they apply after homing and are bypassed
during homing. Return the heads to level or the positive side before stock Z
homing. Automatic recovery from either side needs further investigation of
gate behavior, position sensing or a different homing reference.

## OpenPnP machine setup

OpenPnP runs on the Debian 13 Dell OptiPlex with both cameras, automatic home on enable, coupled
Z mapping and reviewed output commands. Owner reports successful operation and
acceptable homing, with revised motion speed working well so far.
See [current setup status](machine-setup-status.md) and
[commented G-code](openpnp-gcode.md) for the current profile.
Verify travel-limit enforcement and clearances on the assembled machine.
The [feeder host](../../Bing-feeder/V485-feeder/USB_host/README.md) uses the
separate RS485 adapter; it does not relay Smoothieboard commands.
