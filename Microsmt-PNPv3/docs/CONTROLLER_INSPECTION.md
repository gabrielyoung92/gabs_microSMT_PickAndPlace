# Smoothieboard reference

The machine uses a five-axis LPC1769 Smoothieboard connected directly to
OpenPnP on the Debian Dell OptiPlex. The feeder host owns a separate RS485
adapter. See [machine setup](machine-setup-status.md) and
[operating commands](openpnp-gcode.md) for use.

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

Measurements below were recorded on 14 October 2026. Serial checks used
`version`, `M115`, `M114`, `M119`, `mem`, `help`, `get state`, `get status` and
`M503`. The controller answered Idle on USB and after 24 V was connected.
The supply rails were not measured. Reported zero coordinates before homing
were not physical position measurements.

Initial status was millimetres, absolute coordinates, G54, feed 5000.
The Z actuator reported 595 units/s despite its SD setting of 200000 units/min.
Free RAM was 5556 bytes; AHB0/AHB1 free space was 9736/10440 bytes.

## SD files

The FAT `MBED USB DISK` exposed 481 MiB. A read-only copy verified all 19 files
(1,410,020 bytes). Files and hashes are retained under ignored
`.local/v3-modding/controller-2026-10-14/`. This is a file copy, not MCU flash
readback or a tested recovery image.

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `FIRMWARE.CUR` | 388208 | `8fd0b46be73577ffc89cd8588e6c7bc0932d91d2e4959124779d60b8ae3b6dcf` |
| `config.txt` | 20443 | `ae0c257f09de19d43a587d47b40fceda45e6b80f8599e647f678a097027519b3` |

## Axis and output mapping

The source SD configuration gives these pin assignments and rates:

| Axis | Steps per unit | STEP | DIR | ENABLE | Configured max rate per minute | Axis acceleration |
| --- | --- | --- | --- | --- | --- | --- |
| X | 80 | P2.0 | P0.5 inverted | P0.4 | 60000 | 6000 |
| Y | 80 | P2.1 | P0.11 inverted | P0.10 | 48000 | 3000 |
| Z | 168 | P2.2 | P0.20 inverted | P0.19 | 200000 | 15000 |
| A / N1 | 17.7777 | P2.3 | P0.22 | P0.21 | 200000 | 10000 |
| B / N2 | 17.7777 | P2.8 | P2.13 | P4.29 | 200000 | 10000 |

XYZ units are mm; A/B are nozzle rotations in degrees despite the B-axis comment
in the source config. These maximum rates and accelerations are source values;
use the lower [OpenPnP operating profile](openpnp-gcode.md) for the machine.

| Configured output | On / off commands | Pin |
| --- | --- | --- |
| N1 vacuum | M800 / M801 | P2.7 |
| N2 vacuum | M802 / M803 | P2.5 |
| Up camera lights | M804 / M805 | P2.4 |
| Down camera lights | M806 / M807 | P1.22 |
| Vacuum pump | M808 / M809 | P1.23 |
| Drag | M810 / M811 | P2.6 |

Homing search/second-pass speeds are X 50/25, Y 40/25 and Z 50/25 mm/s.
The kill input is P2.12 in toggle mode; its physical operation remains to be tested.
Driver current values are commented out. The manual specifies TMC2209 modules,
Vref adjustment at 24 V and 32 microsteps; verify the fitted drivers/jumpers.

## Motion and endstop checks

All five motor channels showed movement. Initial tests used reduced acceleration:

| Test | Commanded movement | Observation |
| --- | --- | --- |
| X | 1 mm out/back at 1 mm/s; 10 mm at 2/10 mm/s | Gantry moved left/right |
| Y | 10 mm out/back at 10 mm/s | Forward/back movement |
| Z | 2 mm out/back at 2 mm/s | Shared belt moved both heads |
| N1 / A | 15° out/back at 10°/s | N1 rotated; angle not measured |
| N2 / B | 15° out/back at 10°/s | N2 rotated; angle not measured |

X and Y switches each changed their own M119 input from 0 to 1. Z changed with
head position. Released-input and emergency-stop checks still need completing.
Initial homing used `G28 Z`, `G28 X`, then `G28 Y`, with X/Y capped at 10 mm/s,
Z at 2 mm/s and acceleration 20. Each completed Idle; XYZ and all minimum inputs
reported home. OpenPnP now uses its configured combined homing sequence.

## Travel measurements

| Axis | Steps/unit retained | Command / speed | Measured travel |
| --- | --- | --- | --- |
| X | 80 | 300 mm at 100 mm/s, temporary acceleration 500 | 300 mm |
| Y | 80 | 300 mm at 100 mm/s, temporary acceleration 500 | 300 mm |
| Z | 168 | 10 mm at 5 mm/s, temporary acceleration 50 | N2 down 10 mm, N1 up 10 mm |

Positive raw Z lowers N2 and raises N1. At home the heads were level.
Repeatability, rotary scaling and loaded accuracy still need measurement.

Measured X/Y travel is 385/470 mm. Head-to-head Z difference measured 62 mm;
the selected usable range is **Z −30 to +30 mm**, or 60 mm difference. Saved
limits are X 0–385, Y 0–470, Z −30–+30, with halt on an out-of-bounds command.
Limits only apply after homing; runtime enforcement still needs a physical check.
The saved config readback SHA-256 is
`dc4281f0544bff556dff40915cab60cf8921cc62f13bc28a62a5661d13c392c5`.

### Z centre gate

Before homing, put the heads level or N2 below N1. With N2 above N1, the stock
negative Z homing direction moves away from the centre gate toward the stop.
Software limits do not protect the homing search. Recovery from either side of
the gate is not implemented. After manual movement or disabling motors for
measurement, rehome before relying on controller coordinates.

## Evidence

- [Smoothieware console commands](https://smoothieware.org/console-commands)
- [supported G codes](https://smoothieware.org/supported-g-codes.html)
- [initial serial transcript](evidence/controller-2026-10-14/serial-inspection.txt)
- [24 V status transcript](evidence/controller-2026-10-14/serial-24v-inspection.txt)
- [SD config](evidence/controller-2026-10-14/config.txt)
- [first homing transcript](evidence/controller-2026-10-14/first-homing.txt)
- [300 mm calibration command transcript](evidence/controller-2026-10-14/x-calibration-300mm.txt)
- [Y calibration transcript](evidence/controller-2026-10-14/y-calibration-300mm-100mms.txt)
- [Z calibration transcript](evidence/controller-2026-10-14/z-calibration-10mm.txt)
- [motor disable transcript](evidence/controller-2026-10-14/motors-disabled.txt)
- [feeder host](../../Bing-feeder/V485-feeder/USB_host/README.md)
