# KiCad projects and recovery notes

The editable projects and their previews now live beside their source Gerbers in
the matching PCB folders. This folder holds the shared recovery tools and method;
source paths and commands are relative to the repository root.

For delivered machine identities and live inspection evidence, see the
[machine hardware inventory](../../Microsmt-PNPv3/docs/MACHINE_HARDWARE.md), including both cameras.

Editable reference reconstructions from the preserved MicroSMT motherboard PDF,
Bing-feeder schematic,
Gerbers, drill files and flying-probe net data. Use KiCad 10 to open all projects.
Earlier reference files remain compatible with their recorded KiCad versions. Each project keeps its symbol and footprint libraries in `KiCad/libraries/`. All libraries resolve through relative
paths; no personal library configuration is needed.

| Project | Board size | Included objects | Open |
| --- | --- | --- | --- |
| MicroSMT motherboard | 130 × 116.858 mm | 187 source components + 6 plated holes; 4 copper layers; 14 schematic pages | [motherboard.kicad_pro](../../Microsmt-PNPv3/PCB_motherboard/KiCad/motherboard.kicad_pro) |
| Feeder V2 | 53 × 23.5 mm | 38 original components + 4 plated mounting holes | [feeder_v2.kicad_pro](../../Bing-feeder/V3-feeder/PCB_feeder/KiCad/feeder_v2.kicad_pro) |
| Archive labelled N1–N8 | 166 × 25 mm | 8 slots, 2 interconnect headers, 5 mounting holes | [busbar_n1_n8.kicad_pro](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N1-N8/KiCad/busbar_n1_n8.kicad_pro) |
| Archive labelled N9–N16 | 166 × 25 mm | 8 slots, 2 interconnect headers, 5 mounting holes | [busbar_n9_n16.kicad_pro](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N9-N16/KiCad/busbar_n9_n16.kicad_pro) |
| Archive labelled N17–N24 | 166 × 25 mm | 8 slots, 1 interconnect header, 5 mounting holes | [busbar_n17_n24.kicad_pro](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N17-N24/KiCad/busbar_n17_n24.kicad_pro) |

**The N1–N8 archive exports N9–N16 slot nets.** The two first archives contain
identical plotted geometry, drills and probe data despite differing export
metadata/aperture declarations. Their archive-labelled projects are retained
separately to make the source problem visible. They do not establish a valid
N1–N8 board or a complete connected 24-slot assembly.

Each board keeps its connected schematic, routed PCB, project settings and local
libraries in `KiCad/`; reference BOMs, recovery data and validation reports are in
`docs/`. All preview images are in `photos/`. The board README links them together.
Sources: [Bing-feeder](../../Bing-feeder/) and [Microsmt-PNPv3](../../Microsmt-PNPv3/).

## Additional V3 and V485 projects

All remaining Gerber sets now have connected KiCad reference projects. These use
generic passive-pad symbols and retain the supplied manufacturing geometry.
Read each board’s recovery details and validation report before editing.

| Project | Open | Board guide |
| --- | --- | --- |
| V3 controller | [v3_controller.kicad_pro](../../Bing-feeder/V3-Feeder%20Controller/PCB_ControlBoard/KiCad/v3_controller.kicad_pro) | [Guide and reports](../../Bing-feeder/V3-Feeder%20Controller/PCB_ControlBoard/README.md) |
| V485 controller | [v485_controller.kicad_pro](../../Bing-feeder/V485-Feeder%20Controller/PCB_ControlBoard/KiCad/v485_controller.kicad_pro) | [Guide and reports](../../Bing-feeder/V485-Feeder%20Controller/PCB_ControlBoard/README.md) |
| V485 480 mm busbar | [v485_busbar_480mm.kicad_pro](../../Bing-feeder/V485-Feeder%20Controller/PCB_busbar_long_480mm/KiCad/v485_busbar_480mm.kicad_pro) | [Guide and reports](../../Bing-feeder/V485-Feeder%20Controller/PCB_busbar_long_480mm/README.md) |
| V485 short busbar PCB1 | [v485_busbar_180mm_pcb1.kicad_pro](../../Bing-feeder/V485-Feeder%20Controller/PCB_busbar_short_180mm/KiCad/v485_busbar_180mm_pcb1.kicad_pro) | [Guide and reports](../../Bing-feeder/V485-Feeder%20Controller/PCB_busbar_short_180mm/README.md) |
| V485 short busbar PCB2 | [v485_busbar_180mm_pcb2.kicad_pro](../../Bing-feeder/V485-Feeder%20Controller/PCB_busbar_short_180mm/KiCad/v485_busbar_180mm_pcb2.kicad_pro) | [Guide and reports](../../Bing-feeder/V485-Feeder%20Controller/PCB_busbar_short_180mm/README.md) |
| V485 short busbar PCB4 | [v485_busbar_180mm_pcb4.kicad_pro](../../Bing-feeder/V485-Feeder%20Controller/PCB_busbar_short_180mm/KiCad/v485_busbar_180mm_pcb4.kicad_pro) | [Guide and reports](../../Bing-feeder/V485-Feeder%20Controller/PCB_busbar_short_180mm/README.md) |
| V485 display | [v485_display.kicad_pro](../../Bing-feeder/V485-feeder/PCB_display/KiCad/v485_display.kicad_pro) | [Guide and reports](../../Bing-feeder/V485-feeder/PCB_display/README.md) |
| V485 feeder | [v485_feeder.kicad_pro](../../Bing-feeder/V485-feeder/PCB_feeder/KiCad/v485_feeder.kicad_pro) | [Guide and reports](../../Bing-feeder/V485-feeder/PCB_feeder/README.md) |

## Earlier feeder/busbar validation

| Reference | Schematic | Top copper and original silk | Bottom copper and original silk |
| --- | --- | --- | --- |
| Feeder | [Schematic](../../Bing-feeder/V3-feeder/PCB_feeder/photos/kicad-feeder_v2-schematic.png) | [Top](../../Bing-feeder/V3-feeder/PCB_feeder/photos/kicad-feeder_v2-top.png) | [Bottom](../../Bing-feeder/V3-feeder/PCB_feeder/photos/kicad-feeder_v2-bottom.png) |
| N1–N8 archive | [Schematic](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N1-N8/photos/kicad-busbar_n1_n8-schematic.png) | [Top](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N1-N8/photos/kicad-busbar_n1_n8-top.png) | [Bottom](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N1-N8/photos/kicad-busbar_n1_n8-bottom.png) |
| N9–N16 archive | [Schematic](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N9-N16/photos/kicad-busbar_n9_n16-schematic.png) | [Top](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N9-N16/photos/kicad-busbar_n9_n16-top.png) | [Bottom](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N9-N16/photos/kicad-busbar_n9_n16-bottom.png) |
| N17–N24 archive | [Schematic](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N17-N24/photos/kicad-busbar_n17_n24-schematic.png) | [Top](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N17-N24/photos/kicad-busbar_n17_n24-top.png) | [Bottom](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N17-N24/photos/kicad-busbar_n17_n24-bottom.png) |

The five earlier projects were loaded and exported with KiCad 9.0.2. Schematic/PCB parity and unrouted
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
boards. These are recovered references, not a fabrication release. No board
firmware, flashing or hardware validation was performed during this reconstruction.

## Motherboard expansion reference

The new [motherboard project](../../Microsmt-PNPv3/PCB_motherboard/docs/KICAD_RECOVERY.md) has its own library and
[pin audit](../../Microsmt-PNPv3/PCB_motherboard/docs/PIN_AUDIT.md). It reserves three analog vacuum channels for
CFSensor XGZP6847A100KPGN33 sensors (two heads and pump/common manifold) and
the UART RX/TX connection, and identifies unused GPIO candidates for a feeder
module. Its separate [validation](../../Microsmt-PNPv3/PCB_motherboard/docs/validation.json) covers all four
copper layers. The historical results above describe the feeder/busbar projects.

Current sensor implementation uses two nozzle sensors on a separate ESP32-C3
USB board; motherboard ADC reservations remain historical expansion candidates.
See the [sensor plan](../../Microsmt-PNPv3/docs/vacuum-sensors.md).
