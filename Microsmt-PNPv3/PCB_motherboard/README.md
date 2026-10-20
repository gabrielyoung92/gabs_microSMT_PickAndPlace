# PNPv3 motherboard PCB

> **Original: [MicroSMT / Microsmt-PNPv3](https://github.com/microsmt/Microsmt-PNPv3).** [Credits and local changes](../../CREDITS.md).

[Back to collection](../README.md)

Download the Gerber ZIP or click a preview to open it full size.

## Editable KiCad reference

[Open project](KiCad/motherboard.kicad_pro) · [Schematic](KiCad/motherboard.kicad_sch) · [PCB](KiCad/motherboard.kicad_pcb)

This is a local reconstruction from MicroSMT source files, with existing DRC findings. Keep the complete `KiCad/` folder together; its libraries are included in `KiCad/libraries/`.

[Components](docs/components.csv) · [Recovery data](docs/recovery.json) · [Validation](docs/validation.json) · [Mask/paste comparison](docs/mask-paste-comparison.json)

Read the [recovery notes](../../tools/kicad/RECOVERY_NOTES.md) before layout changes or ordering boards. Paths recorded in the recovery JSON are relative to the repository root.

[Motherboard recovery details](docs/KICAD_RECOVERY.md) · [Pin audit](docs/PIN_AUDIT.md) · [MCU pin inventory](docs/mcu-pins.csv)

## Gerber previews — Gerber_PCB

[Download Gerber ZIP](Gerber_PCB.zip)

<table>
<tr>
<td align="center"><a href="photos/Gerber_PCB-top.jpg"><img src="photos/Gerber_PCB-top.jpg" alt="Top" width="240"></a><br><sub>Top</sub></td>
<td align="center"><a href="photos/Gerber_PCB-bottom.jpg"><img src="photos/Gerber_PCB-bottom.jpg" alt="Bottom" width="240"></a><br><sub>Bottom</sub></td>
<td align="center"><a href="photos/Gerber_PCB-iso.jpg"><img src="photos/Gerber_PCB-iso.jpg" alt="Top-side isometric" width="240"></a><br><sub>Top-side isometric</sub></td>
</tr>
</table>

## Schematics, BOMs and supplied notes

- [SCH.pdf](docs/SCH.pdf)

The previews show bare-board geometry from the supplied Gerbers and drill files. Colours and the 1.6 mm rendering thickness are illustrative.

## KiCad previews

These show the recovered editable project; the Gerber previews above show the supplied manufacturing files.

<table>
<tr>
<td align="center"><a href="photos/kicad-schematic-overview.png"><img src="photos/kicad-schematic-overview.png" alt="Recovered schematic" width="240"></a><br><sub>Recovered schematic</sub></td>
<td align="center"><a href="photos/kicad-pcb-top.png"><img src="photos/kicad-pcb-top.png" alt="Recovered PCB top" width="240"></a><br><sub>Recovered PCB top</sub></td>
<td align="center"><a href="photos/kicad-pcb-bottom.png"><img src="photos/kicad-pcb-bottom.png" alt="Recovered PCB bottom" width="240"></a><br><sub>Recovered PCB bottom</sub></td>
</tr>
</table>

[All recovered schematic sheets](photos/kicad-schematic-contact-sheet.png)
