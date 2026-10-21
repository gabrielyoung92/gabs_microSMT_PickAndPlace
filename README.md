# MicroSMT Pick and Place — Reorganised Files

This repository is a reorganised copy of **MicroSMT's [Bing-feeder](https://github.com/microsmt/Bing-feeder) and [Microsmt-PNPv3](https://github.com/microsmt/Microsmt-PNPv3) projects**. The original designs, parts, PCB files, manuals and vendor firmware come from MicroSMT. Files have been moved into clearer folders, with linked previews and documentation added to make them easier to find and use. **Credit for the original work belongs to MicroSMT and its contributors.**

This is an unofficial collection. Local additions, including extra STL exports and firmware changes, were prepared with ChatGPT assistance and are described in [credits and changes](CREDITS.md) and [third-party notices](THIRD_PARTY_NOTICES.md).

Browse **164 3D parts** across 14 galleries, **13 PCB Gerber sets with editable KiCad references**, vendor firmware, assembly manuals and machine setup notes.

| Browse | Contents |
| --- | --- |
| [V485 feeder](Bing-feeder/V485-feeder/README.md) | 8/12/16/24 mm mechanics, shared parts, feeder/display PCBs and STM32 firmware |
| [V485 controller](Bing-feeder/V485-Feeder%20Controller/README.md) | ESP32-C3 controller and 180/480 mm busbars |
| [V3 feeder](Bing-feeder/V3-feeder/README.md) | 8/12/16/24 mm models, shared parts and assembly references |
| [V3 controller](Bing-feeder/V3-Feeder%20Controller/README.md) | Mega2560 sketch, controller PCB and busbars |
| [PNPv3 machine](Microsmt-PNPv3/README.md) | Machine parts, nozzle rack, strip feeders, motherboard and manuals |
| [KiCad recovery tools](tools/kicad/README.md) | Project index, reconstruction tools and editing limits |
| [Machine setup notes](Microsmt-PNPv3/docs/README.md) | OpenPnP setup, controller inspection and sensor plan |

## Visual previews

<p>
<a href="Bing-feeder/V485-feeder/3D_parts_8mm/README.md"><img src="Bing-feeder/V485-feeder/3D_parts_8mm/photos/V485_3D_main-body.jpg" alt="V485 parts gallery" width="360"></a>
<a href="Microsmt-PNPv3/PCB_motherboard/README.md"><img src="Microsmt-PNPv3/PCB_motherboard/photos/Gerber_PCB-iso.jpg" alt="Motherboard PCB gallery" width="360"></a>
</p>

[V485 parts gallery](Bing-feeder/V485-feeder/3D_parts_8mm/README.md) · [Motherboard PCB gallery](Microsmt-PNPv3/PCB_motherboard/README.md)

3D galleries include STEP/STL links, the original preview and eight isometric views per part. PCB galleries include the Gerber ZIP and top, bottom and top-side isometric views. PCB folders keep the original Gerber ZIP filenames, all images in `photos/`, supporting documents in `docs/`, and editable projects with local libraries in `KiCad/` where available.

## Guides and development

- [ESP32-C3 controller: PlatformIO build guide](Bing-feeder/V485-Feeder%20Controller/CODE_esp32C3/README.md)
- [V485 feeder variants: PlatformIO / STM32 HAL build guide](Bing-feeder/V485-feeder/CODE_feeder/README.md)
- [Other STM32 vendor firmware build guide](Bing-feeder/STM32-BUILD.txt)
- [Editable KiCad reference projects](tools/kicad/README.md)
- [Machine setup status](Microsmt-PNPv3/docs/machine-setup-status.md)

V485 CAD now includes 8/12/16/24 mm parts from the 21 October 2026 release. [Update notes](Bing-feeder/UPSTREAM-2026-10-21.md).

## Folder layout

```text
Bing-feeder/             Reorganised MicroSMT feeder/controller files
Microsmt-PNPv3/          Reorganised MicroSMT machine files and manuals
tools/kicad/             KiCad recovery tools and project index
CREDITS.md               Original sources and changes made here
THIRD_PARTY_NOTICES.md   Upstream license and attribution notes
```

Editable KiCad references sit beside the matching PCB Gerbers in the two collections above. Run KiCad recovery commands from the repository root; see [the recovery guide](tools/kicad/RECOVERY_NOTES.md).

## Preview on Windows

Open a folder in VS Code, open its `README.md`, and press **Ctrl + Shift + V**. Keep the `photos/` folders with their READMEs so the local images load. On GitHub, open a collection folder to view its gallery.

