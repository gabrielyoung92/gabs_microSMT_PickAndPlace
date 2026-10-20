# Feeder and busbar KiCad projects

For delivered machine identities and live inspection evidence, see the
[machine hardware inventory](MACHINE_HARDWARE.md), including both cameras.

Editable reference reconstructions from the preserved MicroSMT motherboard PDF,
Bing-feeder schematic,
Gerbers, drill files and flying-probe net data. Open a `.kicad_pro` in KiCad 9 or
newer. The project-local symbol and footprint libraries resolve through relative
paths; no personal library configuration is needed.

| Project | Board size | Included objects | Open |
| --- | --- | --- | --- |
| MicroSMT motherboard | 130 × 116.858 mm | 187 source components + 6 plated holes; 4 copper layers; 14 schematic pages | [motherboard.kicad_pro](motherboard/motherboard.kicad_pro) |
| Feeder V2 | 53 × 23.5 mm | 38 original components + 4 plated mounting holes | [feeder_v2.kicad_pro](feeder_v2/feeder_v2.kicad_pro) |
| Archive labelled N1–N8 | 166 × 25 mm | 8 slots, 2 interconnect headers, 5 mounting holes | [busbar_n1_n8.kicad_pro](busbar_n1_n8/busbar_n1_n8.kicad_pro) |
| Archive labelled N9–N16 | 166 × 25 mm | 8 slots, 2 interconnect headers, 5 mounting holes | [busbar_n9_n16.kicad_pro](busbar_n9_n16/busbar_n9_n16.kicad_pro) |
| Archive labelled N17–N24 | 166 × 25 mm | 8 slots, 1 interconnect header, 5 mounting holes | [busbar_n17_n24.kicad_pro](busbar_n17_n24/busbar_n17_n24.kicad_pro) |

**The N1–N8 archive exports N9–N16 slot nets.** The two first archives contain
identical plotted geometry, drills and probe data despite differing export
metadata/aperture declarations. Their archive-labelled projects are retained
separately to make the source problem visible. They do not establish a valid
N1–N8 board or a complete connected 24-slot assembly.

Each project contains a connected `.kicad_sch`, routed `.kicad_pcb`, project
settings, library tables, a `components.csv` reference BOM, `recovery.json`
provenance/pad map and `validation.json`.
Sources: [Bing-feeder](../../../Bing-feeder/) and [Microsmt-PNPv3](../../../Microsmt-PNPv3/).

## Review the results

| Reference | Schematic | Top copper and original silk | Bottom copper and original silk |
| --- | --- | --- | --- |
| Feeder | [Schematic](previews/feeder_v2-schematic.png) | [Top](previews/feeder_v2-top.png) | [Bottom](previews/feeder_v2-bottom.png) |
| N1–N8 archive | [Schematic](previews/busbar_n1_n8-schematic.png) | [Top](previews/busbar_n1_n8-top.png) | [Bottom](previews/busbar_n1_n8-bottom.png) |
| N9–N16 archive | [Schematic](previews/busbar_n9_n16-schematic.png) | [Top](previews/busbar_n9_n16-top.png) | [Bottom](previews/busbar_n9_n16-bottom.png) |
| N17–N24 archive | [Schematic](previews/busbar_n17_n24-schematic.png) | [Top](previews/busbar_n17_n24-top.png) | [Bottom](previews/busbar_n17_n24-bottom.png) |

KiCad 9.0.2 loads and exports all projects. Schematic/PCB parity and unrouted
connection checks are clear. Every recovered pad net and drill was compared
with the source; the exported front/back copper agrees within the 0.002 mm
comparison tolerance. This is a geometric comparison of parsed CAM, not an
assertion of bit-identical Gerbers or physical measurements.

The busbar schematics have no ERC findings. The feeder has two `label_dangling`
ERC findings for source single-pin PA0 and PA1 nets. The original board layouts
still produce DRC clearance/edge/silkscreen findings under the declared KiCad
rules. Counts and comparison measurements are preserved per project; no findings
are hidden or excluded to obtain a clean report.

Read [RECOVERY_NOTES.md](RECOVERY_NOTES.md) before modifying routing or ordering
boards. These are recovered references, not a fabrication release. The firmware
work remains in [firmware/feeder](../firmware/feeder/); no new board firmware,
flashing or hardware validation was performed during this reconstruction.

## Motherboard expansion reference

The new [motherboard project](motherboard/README.md) has its own library and
[pin audit](motherboard/PIN_AUDIT.md). It reserves three analog vacuum channels for
CFSensor XGZP6847A100KPGN33 sensors (two heads and pump/common manifold) and
the UART RX/TX connection, and identifies unused GPIO candidates for a feeder
module. Its separate [validation](motherboard/validation.json) covers all four
copper layers. The historical results above describe the feeder/busbar projects.

Current sensor implementation uses two nozzle sensors on a separate ESP32-C3
USB board; motherboard ADC reservations remain historical expansion candidates.
See the [sensor plan](../docs/vacuum-sensors.md).
