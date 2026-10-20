# KiCad recovery details

These references were reconstructed from the original MicroSMT Gerbers, drills
and flying-probe data. Original Gerber ZIPs and supplied documents are preserved.
No original editable vendor KiCad project was supplied.

| Project | Source parts | Added hole references | Outline, mm | Schematic pages | Reports |
| --- | --- | --- | --- | --- | --- |
| V485 short busbar PCB1 | 3 | 4 | 161.002 × 15.841 | 2 | [Components](v485_busbar_180mm_pcb1-components.csv) · [Recovery](v485_busbar_180mm_pcb1-recovery.json) · [Validation](v485_busbar_180mm_pcb1-validation.json) · [Mask/paste](v485_busbar_180mm_pcb1-mask-paste-comparison.json) |
| V485 short busbar PCB2 | 4 | 8 | 161.002 × 13.854 | 2 | [Components](v485_busbar_180mm_pcb2-components.csv) · [Recovery](v485_busbar_180mm_pcb2-recovery.json) · [Validation](v485_busbar_180mm_pcb2-validation.json) · [Mask/paste](v485_busbar_180mm_pcb2-mask-paste-comparison.json) |
| V485 short busbar PCB4 | 3 | 4 | 161.002 × 15.841 | 2 | [Components](v485_busbar_180mm_pcb4-components.csv) · [Recovery](v485_busbar_180mm_pcb4-recovery.json) · [Validation](v485_busbar_180mm_pcb4-validation.json) · [Mask/paste](v485_busbar_180mm_pcb4-mask-paste-comparison.json) |

BOM comments/values are used where supplied. Busbar parts without a BOM remain
labelled “Unspecified in source BOM”. Generic PAD labels are not device pin-function
claims. `HREC` references identify unreferenced source holes; their purpose is
unverified. Non-plated holes are mechanical objects, not electrical connections.

The collection calls these “180 mm” busbars. Each supplied PCB outline measures
about **161.002 mm** long; the source archive names and three variants are retained.

Copper contours preserve the final plotted copper, including copper beneath
tracks and pads. Moving a trace alone leaves that copper behind. Replace the
affected recovered pours deliberately during a redesign. Mask/paste differences
are reported separately; a copper match is not a fabrication release. Component
bodies, courtyards, 3D models and actual stackup/thickness are not established.

Validation reports record native KiCad checks, numbered-pad nets/positions,
plated/non-plated drills and front/back copper comparisons with a 0.002 mm
tolerance. Single-pin-label ERC warnings and original-layout DRC findings are
retained; no exclusions were added. Generic passive pins do not provide a device
electrical-rules audit. Full native reports are in ignored `build/kicad/`.

Source paths in recovery JSON are relative to the repository root, where the
[recovery tool](../../../../tools/kicad/recover_remaining.py) runs. See the
[shared method and rebuild instructions](../../../../tools/kicad/RECOVERY_NOTES.md).
