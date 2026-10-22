# KiCad projects and recovery notes

These tools were used to rebuild editable KiCad projects from MicroSMT’s schematics, Gerbers, drill files and flying-probe data. The projects and pictures are in their matching PCB folders; this folder holds the tools and [recovery notes](RECOVERY_NOTES.md).

Open the projects in **KiCad 10**. Keep each `KiCad/` folder together: the symbol and footprint libraries are in `KiCad/libraries/` and use relative paths, so they don’t need your personal KiCad libraries. Earlier checks used the KiCad versions recorded in their reports.

Run the tools from the repository root. They can overwrite generated boards and reports, so use a disposable checkout after making manual edits. The [hardware inventory](../../Microsmt-PNPv3/docs/MACHINE_HARDWARE.md) covers the actual machine and both cameras.

| Project | Board size | Included objects | Open |
| --- | --- | --- | --- |
| MicroSMT motherboard | 130 × 116.858 mm | 187 source components + 6 plated holes; 4 copper layers; 14 schematic pages | [motherboard.kicad_pro](../../Microsmt-PNPv3/PCB_motherboard/KiCad/motherboard.kicad_pro) |
| Feeder V2 | 53 × 23.5 mm | 38 original components + 4 plated mounting holes | [feeder_v2.kicad_pro](../../Bing-feeder/V3-feeder/PCB_feeder/KiCad/feeder_v2.kicad_pro) |
| Archive labelled N1–N8 | 166 × 25 mm | 8 slots, 2 interconnect headers, 5 mounting holes | [busbar_n1_n8.kicad_pro](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N1-N8/KiCad/busbar_n1_n8.kicad_pro) |
| Archive labelled N9–N16 | 166 × 25 mm | 8 slots, 2 interconnect headers, 5 mounting holes | [busbar_n9_n16.kicad_pro](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N9-N16/KiCad/busbar_n9_n16.kicad_pro) |
| Archive labelled N17–N24 | 166 × 25 mm | 8 slots, 1 interconnect header, 5 mounting holes | [busbar_n17_n24.kicad_pro](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N17-N24/KiCad/busbar_n17_n24.kicad_pro) |

**The ZIP labelled N1–N8 contains N9–N16 slot signals.** Its board geometry, drills and probe data match the N9–N16 ZIP; only export metadata and aperture declarations differ. Both projects are kept under their original labels so the mix-up is visible. These files don’t provide a confirmed N1–N8 board or a complete connected 24-slot assembly.

Each board folder has its schematic, routed PCB, project settings and libraries in `KiCad/`. Parts lists and check reports are in `docs/`, and pictures are in `photos/`. The board’s README links to them.
Sources: [Bing-feeder](../../Bing-feeder/) and [Microsmt-PNPv3](../../Microsmt-PNPv3/).

## Additional V3 and V485 projects

These boards also have rebuilt KiCad projects. Their generic pin symbols show the pad connections, and their layouts follow the supplied board geometry. Read each board’s recovery notes and check report before editing.

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

## Earlier feeder and busbar checks

| Reference | Schematic | Top copper and original silk | Bottom copper and original silk |
| --- | --- | --- | --- |
| Feeder | [Schematic](../../Bing-feeder/V3-feeder/PCB_feeder/photos/kicad-feeder_v2-schematic.png) | [Top](../../Bing-feeder/V3-feeder/PCB_feeder/photos/kicad-feeder_v2-top.png) | [Bottom](../../Bing-feeder/V3-feeder/PCB_feeder/photos/kicad-feeder_v2-bottom.png) |
| N1–N8 archive | [Schematic](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N1-N8/photos/kicad-busbar_n1_n8-schematic.png) | [Top](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N1-N8/photos/kicad-busbar_n1_n8-top.png) | [Bottom](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N1-N8/photos/kicad-busbar_n1_n8-bottom.png) |
| N9–N16 archive | [Schematic](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N9-N16/photos/kicad-busbar_n9_n16-schematic.png) | [Top](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N9-N16/photos/kicad-busbar_n9_n16-top.png) | [Bottom](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N9-N16/photos/kicad-busbar_n9_n16-bottom.png) |
| N17–N24 archive | [Schematic](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N17-N24/photos/kicad-busbar_n17_n24-schematic.png) | [Top](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N17-N24/photos/kicad-busbar_n17_n24-top.png) | [Bottom](../../Bing-feeder/V3-Feeder%20Controller/PCB_busbar_N17-N24/photos/kicad-busbar_n17_n24-bottom.png) |

The five earlier projects were opened and exported with KiCad 9.0.2. The schematic/PCB consistency checks passed, with no unrouted connections. Every pad connection and drill was compared with the source, and exported front/back copper matched within the 0.002 mm comparison tolerance. That checks the file geometry; it doesn’t mean the Gerbers are byte-for-byte copies or that a physical board has been measured.

The busbar schematics pass ERC. The feeder still has two `label_dangling` ERC findings for the original single-pin PA0 and PA1 nets. DRC also reports clearance, board-edge and silkscreen issues in the original layouts. Each project’s reports keep the counts and measurements; nothing was hidden or excluded to make a check pass.

Read [RECOVERY_NOTES.md](RECOVERY_NOTES.md) before changing tracks or ordering boards. These are rebuilt reference projects, not files cleared for manufacture. The recovery work didn’t flash firmware or test hardware.

## Motherboard expansion reference

The [motherboard project](../../Microsmt-PNPv3/PCB_motherboard/docs/KICAD_RECOVERY.md) has its own library, [pin audit](../../Microsmt-PNPv3/PCB_motherboard/docs/PIN_AUDIT.md) and [four-layer check report](../../Microsmt-PNPv3/PCB_motherboard/docs/validation.json). The expansion reference reserves three analogue channels for XGZP6847A100KPGN33 sensors—two heads and a pump/common manifold—plus UART RX/TX. It also lists possible unused GPIOs for a feeder module. The earlier check results above apply to the feeder and busbars.

The current [sensor plan](../../Microsmt-PNPv3/docs/vacuum-sensors.md) uses two nozzle sensors on a separate ESP32-C3 USB board. The motherboard ADC channels remain an earlier expansion option.
