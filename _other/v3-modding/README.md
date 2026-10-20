# MicroSMT feeder hardware and firmware

An independent MicroSMT PNPv3 project, starting with smart Bing feeder firmware
and a separate feeder controller for OpenPnP.

## Current status

Feeder development remains early and its new hardware/firmware has not been
physically validated. The stock machine now runs OpenPnP on a Raspberry Pi 5,
with owner-observed homing/motion, both camera streams and identified lighting
outputs. Assembly continues; calibration is deferred. See the
[current machine status](docs/machine-setup-status.md).

The canonical vendor files are in [../../Bing-feeder/](../../Bing-feeder/)
and [../../Microsmt-PNPv3/](../../Microsmt-PNPv3/).
The duplicate `vendor/` imports were removed during workspace cleanup.
Hardware recovery tools use those source directories at the repository root.

PlatformIO now builds a candidate STM32 feeder bench image and USB single-wire
bridge images for Pico 2 and Pico 2 W. The W supports optional Wi-Fi TCP
diagnostics. Readable commands, bounded address scans, ping, status, raw inputs
and UID are implemented; **motor commands remain inhibited**. Builds and simulated exchanges
pass, but no physical hardware has been flashed or validated. Start with the
[VS Code / PlatformIO guide](firmware/README.md) and
[controller setup](docs/bridge-controller.md).

Editable KiCad reference projects now cover the LPC1769 motherboard, feeder V2
board and all three supplied busbar archives. Start with [hardware/README.md](hardware/README.md) for
project links, previews, validation and source discrepancies.

## Direction

The current [vacuum sensor plan](docs/vacuum-sensors.md) uses two
XGZP6847A100KPGN33 sensors on a separate ESP32-C3 USB board, one per nozzle.


- OpenPnP remains responsible for the placement workflow.
- Retain the stock LPC1769 / Smoothieware PnP motion system initially.
- Preserve the Bing feeder's optical indexing and mechanical operation.
- Develop an addressed feeder bus with command acceptance, busy, completion and
  fault reporting. Acknowledgement alone must never mean the tape has advanced.
- Separate persistent feeder identity from physical slot identity; investigate
  Photon-style integration and a local 1-Wire slot EEPROM.
- Choose the physical layer after checking the actual feeder revision. Custom
  single-wire, LIN and RS485 remain candidates.

No project-wide license has been selected yet; upstream notices remain intact.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Layout

| Path | Purpose |
| --- | --- |
| `../../{Bing-feeder,Microsmt-PNPv3}/` | Shared vendor parts, firmware, manuals and PCB sources |
| `hardware/` | Native KiCad feeder/busbar projects, shared libraries and recovery evidence |
| `firmware/feeder/` | Our feeder core and its integration contract |
| `tests/` | Host-side behavioral checks |
| `tools/` | Firmware bench and hardware recovery tools |
| `docs/feeder-source-audit.md` | Findings from the actual source and schematic |
| `.local/` | Ignored local working material |

## Machine setup

See [OpenPnP commands and operating limits](docs/openpnp-gcode.md) for
the reviewed controller command blocks, comments, output mappings and validation.

## Work locally

Open `MicroSMT.code-workspace` in VS Code, install the recommended PlatformIO
extension, then select an environment's Build action in Project Tasks. From its
Core terminal:

```sh
pio run
python tools/check.py
```

The check script needs Python 3 and a desktop C compiler. Make is optional;
`make check` and `make arm-check` remain supported. See the
[bus wiring/protocol guide](docs/feeder-bus-bench.md) and
[build validation](docs/firmware-build-validation.md).

Start with the [source audit](docs/feeder-source-audit.md) and
[TODO.md](TODO.md) before selecting hardware or extending the firmware.
