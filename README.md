# MicroSMT pick and place files

This is a working collection of [MicroSMT’s Bing feeders](https://github.com/microsmt/Bing-feeder) and [PNPv3 machine files](https://github.com/microsmt/Microsmt-PNPv3). It brings the models, board files, firmware and manuals together, with previews to help find the right part.

The original designs belong to MicroSMT and its contributors. This is an unofficial copy, with local changes made with ChatGPT assistance. See [credits](CREDITS.md) and [third-party notices](THIRD_PARTY_NOTICES.md) for the sources and what changed.

| Browse | Contents |
| --- | --- |
| [Feeder dashboard and PC host](Bing-feeder/V485-feeder/USB_host/README.md) | Port 80 web interface, direct USB–RS485, feeder TCP, parts/packages and job stock |
| [V485 feeder](Bing-feeder/V485-feeder/README.md) | 8/12/16/24 mm mechanics, PCBs and universal STM32 firmware 0.1.2 |
| [V485 controller](Bing-feeder/V485-Feeder%20Controller/README.md) | ESP32-C3 controller and 180/480 mm busbars |
| [V3 feeder](Bing-feeder/V3-feeder/README.md) | 8/12/16/24 mm models, shared parts and assembly references |
| [V3 controller](Bing-feeder/V3-Feeder%20Controller/README.md) | Mega2560 sketch, controller PCB and busbars |
| [PNPv3 machine](Microsmt-PNPv3/README.md) | Machine parts, nozzle rack, strip feeders, motherboard and manuals |
| [KiCad recovery tools](tools/kicad/README.md) | Project index, reconstruction tools and editing limits |
| [Machine setup notes](Microsmt-PNPv3/docs/README.md) | OpenPnP setup, controller inspection and sensor plan |

## Have a look

<p>
<a href="Bing-feeder/V485-feeder/3D_parts_8mm/README.md"><img src="Bing-feeder/V485-feeder/3D_parts_8mm/photos/V485_3D_main-body.jpg" alt="V485 parts gallery" width="360"></a>
<a href="Microsmt-PNPv3/PCB_motherboard/README.md"><img src="Microsmt-PNPv3/PCB_motherboard/photos/Gerber_PCB-iso.jpg" alt="Motherboard PCB gallery" width="360"></a>
</p>

[V485 parts gallery](Bing-feeder/V485-feeder/3D_parts_8mm/README.md) · [Motherboard PCB gallery](Microsmt-PNPv3/PCB_motherboard/README.md)

Each part has a picture, download links and extra views. STL files are for printing; STEP files are available for most parts if you need to edit them. Board folders have Gerber ZIPs, previews and rebuilt KiCad projects. Photos are in `photos/`, and schematics, parts lists and notes are in `docs/`.

## Guides and work in progress

- [V485 missing parts and questions for Bing](V485-MISSING-PARTS.md)
- [ESP32-C3 controller: PlatformIO build guide](Bing-feeder/V485-Feeder%20Controller/CODE_esp32C3/README.md)
- [Powered-feeder dashboard: setup, firmware updates and OpenPnP connection](Bing-feeder/V485-feeder/USB_host/README.md)
- [V485 feeder variants: PlatformIO / STM32 HAL build guide](Bing-feeder/V485-feeder/CODE_feeder/README.md)
- [Other STM32 vendor firmware build guide](Bing-feeder/STM32-BUILD.txt)
- [Editable KiCad reference projects](tools/kicad/README.md)
- [Machine setup status](Microsmt-PNPv3/docs/machine-setup-status.md)

## This machine's software

The machine computer is a Dell OptiPlex running Debian 13 and OpenPnP.
OpenPnP connects directly to the Smoothieboard and cameras, and handles pickup
teaching, nozzle management and jobs. The feeder host owns the USB–RS485 adapter
and exposes one local TCP port, `127.0.0.1:5001`, for feeder advances. The web
interface is at `http://machine-hostname/`, without authentication or TLS.

The dashboard provides feeder state/errors, stock, motor/switch configuration,
input tests and individual/bulk firmware updates. It also offers compact native
OpenPnP part/package editing and a remaining-job stock check. Tip compatibility
is selected through packages; physical nozzle setup stays in OpenPnP.

Current feeder firmware is **0.1.2**, one application for all four tape widths.
The installed bootloader handles updates. Building creates the web firmware
bundle automatically; connected outdated units can then be queued from the page.

| Source | Location |
| --- | --- |
| Computer service, dashboard and OpenPnP script | [`Bing-feeder/V485-feeder/USB_host/`](Bing-feeder/V485-feeder/USB_host/README.md) |
| Feeder application, loader and serial tools | [`Bing-feeder/V485-feeder/CODE_feeder/`](Bing-feeder/V485-feeder/CODE_feeder/README.md) |
| Remaining bench work | [TODO.md](TODO.md) |

Use the [host guide](Bing-feeder/V485-feeder/USB_host/README.md) for installation
and the [firmware guide](Bing-feeder/V485-feeder/CODE_feeder/README.md) for builds.
Private machine data, SSH keys and generated firmware bundles stay outside Git.

## Folder layout

```text
Bing-feeder/             Reorganised MicroSMT feeder/controller files
Microsmt-PNPv3/          Reorganised MicroSMT machine files and manuals
tools/kicad/             KiCad recovery tools and project index
CREDITS.md               Original sources and changes made here
THIRD_PARTY_NOTICES.md   Upstream license and attribution notes
```

The KiCad projects sit beside their matching Gerbers. They were rebuilt from MicroSMT’s files, so read [the recovery guide](tools/kicad/RECOVERY_NOTES.md) before changing a layout or ordering boards. Run the recovery tools from this repository’s root folder.

## Preview on Windows

In VS Code, open a `README.md` and press **Ctrl + Shift + V** to see the pictures. Keep the `photos/` folders beside the READMEs. On GitHub, just open a folder and scroll down to its gallery.

