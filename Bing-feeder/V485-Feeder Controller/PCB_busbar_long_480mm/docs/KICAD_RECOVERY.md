# KiCad recovery details

Rebuilt from MicroSMT Gerbers, drills and flying-probe data. Source ZIPs and
documents are preserved; the editable KiCad files are local reconstructions.

| Project | Source parts | Added hole references | Outline, mm | Schematic pages | Reports |
| --- | --- | --- | --- | --- | --- |
| V485 480 mm busbar | 4 | 0 | 480 × 15.841 | 2 | [Components](components.csv) · [Recovery](recovery.json) · [Validation](validation.json) · [Mask/paste](mask-paste-comparison.json) |

- Values come from the supplied BOM; missing values are labelled unspecified.
- Generic PAD symbols show connectivity, not device pin functions.
- `HREC` marks holes without source references. Non-plated holes are mechanical.

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
