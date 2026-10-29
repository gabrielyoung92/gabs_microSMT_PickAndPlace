# Machine setup

The machine computer is a Dell OptiPlex running Debian 13 and OpenPnP.
The LPC1769 Smoothieboard retains its direct USB serial connection to OpenPnP.
The powered feeders use a separate direct USB–RS485 adapter and PC host.

## Software responsibilities

| Component | Responsibility |
| --- | --- |
| OpenPnP | Motion, cameras, pickup positions, nozzle setup, calibration and jobs |
| Feeder host | RS485, local feeder TCP, dashboard, stock and application updates |
| Feeder firmware 0.1.2 | Index/peel motors, tension switch, buttons, settings, faults and input tests |

The host exposes `127.0.0.1:5001` for OpenPnP feeder commands and HTTP port 80 for
the dashboard. The optional OpenPnP script uses loopback port 5004 for catalogue
edits and reading job requirements. It does not control motion or stream cameras.
See the [host installation guide](../../Bing-feeder/V485-feeder/USB_host/README.md).

## Feeder operation

One universal image supports all tape widths. Application builds automatically
produce the dashboard bundle. Use a row's Update or Update all outdated, then
inspect the queue results. The installed bootloader is left in place.

The overview shows responding/offline feeders, firmware, errors, configured
advance and stock. Settings and reels use popovers. The input test inhibits both
motors while checking switch/buttons/sensor. OpenPnP remains the place to teach
pickup and nozzle changer locations and run placement jobs.

Parts/packages can be edited through the web companion; they remain native
OpenPnP records. Compatible tips are assigned through the part's package. The
Job stock page checks remaining demand against tracked reels, not overall
machine readiness. Other feeder types stay in OpenPnP.

## Machine-side work

- Verify loaded-tape feed distance and switch-controlled peel completion.
- Teach and test nozzle changer positions and N1/N2 reach.
- Check vacuum routing, suction and release independently on both nozzles.
- Calibrate camera focus/scale, nozzle offsets, pickup heights and bottom vision.
- Check clearance, endstops, stop behaviour and motion limits before placement.
- Complete a feed/pick/place trial and compare stock estimates with actual usage.

The [project TODO](../../TODO.md) tracks the remaining work. Hardware descriptions
and command mappings are in [hardware inventory](MACHINE_HARDWARE.md) and
[OpenPnP commands](openpnp-gcode.md). Private machine settings and credentials are
not included in these public instructions.
