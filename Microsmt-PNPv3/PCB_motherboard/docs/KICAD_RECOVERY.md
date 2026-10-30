# MicroSMT LPC1769 motherboard reference

Open [motherboard.kicad_pro](../KiCad/motherboard.kicad_pro) in KiCad 9 or newer.
The project contains a four-layer native PCB, a connected 14-page hierarchical
schematic, portable local libraries, a component inventory and source evidence.

- [Schematic](../KiCad/motherboard.kicad_sch): open the functional sheet symbols for the MCU,
  five stepper channels, digital potentiometers, endstops, interfaces, power and passives.
- [PCB](../KiCad/motherboard.kicad_pcb): numbered pads, linked footprints, tracks, vias,
  preserved copper contours, source silkscreen and board outline.
- [Pin audit](PIN_AUDIT.md): MCU/connector mapping and spare GPIO/ADC candidates.
  This machine uses a separate USB board for its planned vacuum sensors.
- [Complete MCU inventory](mcu-pins.csv): all 100 package pins and source net endpoints.
- [Components](components.csv): source references, values and recovered footprint IDs.
- [Recovery model](recovery.json): source/member hashes, numbered pads, inferred holes
  and normalization of duplicate source probe rows.
- [Validation](validation.json): native net/parity checks, drill/pad comparisons,
  four copper-layer CAM comparisons and unsuppressed ERC/DRC counts.

## Source and interpretation

Sources: [schematic PDF](SCH.pdf)
and [Gerber ZIP](../Gerber_PCB.zip). Source data establishes 187 components and 648
unique numbered component pads. Six unreferenced plated mounting holes are added
as explicitly inferred MH references. The CAM outline is approximately
130.000 x 116.858 mm. Actual board thickness, stackup materials and copper weight
are not established; 1.6 mm is a working default.

The probe export also includes 567 synthetic PAD references, with 745 pin rows
that duplicate physical component pads. Each removed alias is matched by position,
layer and net and is recorded in recovery.json. Repeated component/probe rows are
collapsed only after agreement checks. The two drill exports are deduplicated;
33 extremely short axis-aligned slots are retained as oblong holes, rather than
silently changed into circles.

The physical pad numbers from CAM are authoritative for this reconstruction.
Connector letters, source references such as X/Y/Z, diode A/C pads and MOSFET
G/D/S pads remain explicit. PDF-only alternative protection scheme D2 is not
added to the PCB that exports Q10. Switch anchor contacts, unused regulator/device
pads and MicroSD shield/contact discrepancies remain as exported.
Values absent from the PDF are marked unspecified. Generic source packages use
passive schematic electrical types where an exact functional pin interpretation
is not established. The LPC symbol is flattened from KiCad's LPC1769FBD100
reference; slash characters in three debug pin names are normalized to underscores
so native XML/PCB unconnected-net names agree. The KiCad library licence
is retained in [libraries/LICENSE.KiCad-symbols.txt](../KiCad/libraries/LICENSE.KiCad-symbols.txt).

## Editing limits

This is an editable reference, not a fabrication release. Gerbers do not contain
the original zone design intent. Recovered zones preserve the final plotted copper,
including copper underneath native same-net pads/tracks. Moving only a track or
component leaves old copper in those contours. Replace affected recovered pours
and reroute deliberately when creating a redesign.

Original silkscreen is native graphic geometry; it is not text attached to
individual footprints. Body/courtyard outlines, connector part identities and
3D models are not inferred. DRC findings are reported under working KiCad rules;
none are hidden by exclusions. Read the project-wide
[recovery notes](../../../tools/kicad/RECOVERY_NOTES.md) before layout changes.

## Validation evidence

Native KiCad 9.0.2 checks found no schematic/PCB net mismatches, no unrouted
connections, no library mismatch findings and no ERC findings. All 654 numbered
pads (including mounting holes) and 1,676 plated drills were matched. All four
copper layers agree with the CAM within the 0.002 mm comparison tolerance.
The source's 33 short slots remain oblong.

The recorded DRC findings are 110 clearance, 27 copper-edge clearance,
19 silkscreen-edge clearance, 89 silkscreen-over-copper and 21 solder-mask bridges.
Native pad-generated mask openings are an approximation: the top mask's symmetric
difference from CAM is 1.932 mm² across a 1,509.647 mm² source area. Bottom mask
and top paste differences are below 0.001 mm². See
[mask/paste comparison](mask-paste-comparison.json); the copper comparison does not
establish an exact mask match or a fabrication release.

## Reproduce in a disposable checkout

Run these commands from the repository root, using the
dependency/runtime setup in the recovery notes. The motherboard tools
only generate this project and its separate MicroSMT_Motherboard libraries:

```sh
python tools/kicad/build_motherboard.py
python tools/kicad/build_motherboard_schematic.py
python tools/kicad/audit_motherboard_pins.py
python tools/kicad/validate_motherboard.py
python tools/kicad/render_motherboard.py
```

The generator overwrites generated motherboard files. Preserve manual work before
running it again. The original feeder/busbar generators retain their original
project list and should not be used to regenerate or prune the motherboard library.

The sensor plan uses two nozzle sensors on a separate ESP32-C3 USB board;
the motherboard ADC entries are spare-pin references.
See the [sensor plan](../../docs/vacuum-sensors.md).

[PCB top](../photos/kicad-pcb-top.png) · [PCB bottom](../photos/kicad-pcb-bottom.png) · [Schematic overview](../photos/kicad-schematic-overview.png) · [All sheets](../photos/kicad-schematic-contact-sheet.png)

Recovery reports and inventories are in this `docs/` folder.

Source paths in the recovery JSON are relative to the repository root.
