# KiCad recovery details

Rebuilt from MicroSMT Gerbers, drills and flying-probe data. Source ZIPs and
documents are preserved; the editable KiCad files are local reconstructions.

| Project | Source parts | Added hole references | Outline, mm | Schematic pages | Reports |
| --- | --- | --- | --- | --- | --- |
| V485 short busbar PCB1 | 3 | 4 | 161.002 × 15.841 | 2 | [Components](v485_busbar_180mm_pcb1-components.csv) · [Recovery](v485_busbar_180mm_pcb1-recovery.json) · [Validation](v485_busbar_180mm_pcb1-validation.json) · [Mask/paste](v485_busbar_180mm_pcb1-mask-paste-comparison.json) |
| V485 short busbar PCB2 | 4 | 8 | 161.002 × 13.854 | 2 | [Components](v485_busbar_180mm_pcb2-components.csv) · [Recovery](v485_busbar_180mm_pcb2-recovery.json) · [Validation](v485_busbar_180mm_pcb2-validation.json) · [Mask/paste](v485_busbar_180mm_pcb2-mask-paste-comparison.json) |
| V485 short busbar PCB4 | 3 | 4 | 161.002 × 15.841 | 2 | [Components](v485_busbar_180mm_pcb4-components.csv) · [Recovery](v485_busbar_180mm_pcb4-recovery.json) · [Validation](v485_busbar_180mm_pcb4-validation.json) · [Mask/paste](v485_busbar_180mm_pcb4-mask-paste-comparison.json) |

- Values come from the supplied BOM; missing values are labelled unspecified.
- Generic PAD symbols show connectivity, not device pin functions.
- `HREC` marks holes without source references. Non-plated holes are mechanical.

The collection calls these “180 mm” busbars. Each supplied PCB outline measures
about **161.002 mm** long; the source archive names and three variants are retained.

Recovered pours contain the plotted copper beneath tracks and pads. Replace
affected pours when moving tracks; moving a trace alone leaves its copper behind.
Mask/paste differences have separate reports. Bodies, courtyards, 3D models and
actual stackup/thickness are not supplied.

Reports cover pad nets/positions, drills, ERC/DRC and copper comparison at
0.002 mm tolerance. Findings remain visible without exclusions. Generic passive
pins cannot check device electrical rules. Full reports are in `build/kicad/`.

Source paths in recovery JSON are relative to the repository root, where the
[recovery tool](../../../../tools/kicad/recover_remaining.py) runs. See the
[shared method and rebuild instructions](../../../../tools/kicad/RECOVERY_NOTES.md).
