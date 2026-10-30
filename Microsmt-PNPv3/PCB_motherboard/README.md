# PNPv3 motherboard PCB

> Designs and original files by [MicroSMT](https://github.com/microsmt/Microsmt-PNPv3). [Credits and local changes](../../CREDITS.md).

[Back to collection](../README.md)

Gerbers, editable KiCad files and previews are below.

## KiCad files

[Open project](KiCad/motherboard.kicad_pro) · [Schematic](KiCad/motherboard.kicad_sch) · [PCB](KiCad/motherboard.kicad_pcb)

Rebuilt from MicroSMT source files. Keep `KiCad/` together for its local libraries. Review the DRC results before editing or ordering.

[Components](docs/components.csv) · [Recovery data](docs/recovery.json) · [Validation](docs/validation.json) · [Mask/paste comparison](docs/mask-paste-comparison.json)

Read the [recovery notes](../../tools/kicad/RECOVERY_NOTES.md) before layout changes or ordering boards. Paths in the recovery JSON start at the repository root.

[Motherboard recovery details](docs/KICAD_RECOVERY.md) · [Pin audit](docs/PIN_AUDIT.md) · [MCU pin inventory](docs/mcu-pins.csv)

## Original board views

[Download Gerber ZIP](Gerber_PCB.zip)

<table>
<tr>
<td align="center"><a href="photos/Gerber_PCB-top.jpg"><img src="photos/Gerber_PCB-top.jpg" alt="Top" width="240"></a><br><sub>Top</sub></td>
<td align="center"><a href="photos/Gerber_PCB-bottom.jpg"><img src="photos/Gerber_PCB-bottom.jpg" alt="Bottom" width="240"></a><br><sub>Bottom</sub></td>
<td align="center"><a href="photos/Gerber_PCB-iso.jpg"><img src="photos/Gerber_PCB-iso.jpg" alt="Top-side isometric" width="240"></a><br><sub>Top-side isometric</sub></td>
</tr>
</table>

## Schematics, parts lists and notes

- [SCH.pdf](docs/SCH.pdf)

Gerber previews use display colours and an assumed 1.6 mm thickness; use source data for manufacturing dimensions.

## KiCad previews

KiCad reconstruction views; source Gerber views are above.

<table>
<tr>
<td align="center"><a href="photos/kicad-schematic-overview.png"><img src="photos/kicad-schematic-overview.png" alt="Recovered schematic" width="240"></a><br><sub>Recovered schematic</sub></td>
<td align="center"><a href="photos/kicad-pcb-top.png"><img src="photos/kicad-pcb-top.png" alt="Recovered PCB top" width="240"></a><br><sub>Recovered PCB top</sub></td>
<td align="center"><a href="photos/kicad-pcb-bottom.png"><img src="photos/kicad-pcb-bottom.png" alt="Recovered PCB bottom" width="240"></a><br><sub>Recovered PCB bottom</sub></td>
</tr>
</table>

[All recovered schematic sheets](photos/kicad-schematic-contact-sheet.png)
