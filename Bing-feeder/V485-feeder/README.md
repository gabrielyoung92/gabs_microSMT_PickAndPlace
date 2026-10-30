# V485 feeder

> Designs and original files by [MicroSMT](https://github.com/microsmt/Bing-feeder). [Credits and local changes](../../CREDITS.md).

Choose your feeder width below. These folders include the wider V485 parts added in the 21 October 2026 download, along with the boards and local firmware.

| Browse | Contents |
| --- | --- |
| [8 mm parts](3D_parts_8mm/README.md) | 23 parts with STEP/STL links and nine previews per part |
| [12 mm parts](3D_parts_12mm/README.md) | 11 parts with STEP/STL links and nine previews per part |
| [16 mm parts](3D_parts_16mm/README.md) | 10 parts with STEP/STL links and nine previews per part |
| [24 mm parts](3D_parts_24mm/README.md) | 10 parts with STEP/STL links and nine previews per part |
| [Shared wider-feeder parts](3D_parts_shared/README.md) | 5 parts with STEP/STL links and nine previews per part |
| [Feeder PCB](PCB_feeder/README.md) | Gerber ZIP, schematic, BOM and three board views |
| [Display PCB](PCB_display/README.md) | Gerber ZIP, schematic, BOM and three board views |
| [USB host service](USB_host/README.md) | Port 80 dashboard, direct USB–RS485, feeder TCP, stock/configuration and firmware queue |
| [Feeder firmware](CODE_feeder/README.md) | Version 0.1.3: universal application, switch-controlled peel completion and motor-off input tests |

Shared wider-feeder parts are in [their own folder](3D_parts_shared/README.md).
See [missing parts](../../V485-MISSING-PARTS.md) and the
[source comparison](../UPSTREAM-2026-10-25.md) for file coverage.

## Software on this machine

The [PC host](USB_host/README.md) manages the powered feeders. OpenPnP owns the
Smoothieboard serial connection, cameras, pickup locations, physical nozzle setup
and jobs. The host exposes feeder TCP on `127.0.0.1:5001` and a compact web page
on port 80. Normal firmware updates use the installed bootloader; one universal
application covers 8/12/16/24 mm units.

