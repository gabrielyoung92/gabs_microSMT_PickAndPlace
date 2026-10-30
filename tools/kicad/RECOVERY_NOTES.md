# Recovery method, evidence and limits

## Source data

The feeder schematic PNG provides component values and functional context.
`FlyingProbeTesting.json` supplies references, pad numbers, net names, package
centres and orientation. Gerbers supply copper and printed geometry. Excellon
supplies plated drill diameters and positions. The source archives and all their
member hashes are identified in each project's `recovery.json`; the preserved
repository-wide manifest additionally hashes the archive files themselves.

The feeder V2, three V3 busbars and motherboard have front-side source components.
The V485 references retain front/back component sides. Repeated top/bottom probe rows for
plated pads are collapsed into one physical pad. The separate via drill file
repeats holes from the through-drill file; those holes are deduplicated by position
and checked for conflicting diameters. The parser reports the source's G90
statement occurring after the header, but reads its explicit metric coordinates.

Copper is composed in Gerber drawing order, including clear-polarity operations.
Connected islands are linked through plated holes and seeded with test-data net
names. No island joins conflicting named source nets. Unnamed interconnect nets
retain neutral `RECOVERED_*` names; no unobserved signal identities are invented.
Meaningful names replace anonymous feeder nets via the recorded alias table.

## Native editing and libraries

- Components are native KiCad footprints with numbered pads and schematic links.
  The schematics contain real symbols, wires, net labels and no-connect markers.
  Native tracks/arcs/vias recover the source centre lines, widths and drills.
- Exact CAM pad geometry is in each feeder/busbar project’s `KiCad/libraries/MicroSMT_Recovered.pretty`. A stock
  nominal package is not silently substituted for a differently dimensioned
  exported pad pattern. The geometry hash distinguishes recovered variants.
  Standard schematic symbols come from KiCad 9.0.2; the library license and
  electronic-design exception are preserved alongside them.
- AMS1117 has a source-specific four-pad symbol. The TC1508A and four-pad switch
  have explicit source pad numbers. The MCU uses a flattened STM32F103C8Tx symbol
  **conditionally**, with the source's incomplete `STM32C8T6` value retained.
- Isolated synthetic source nets become explicit schematic no-connects, then
  receive KiCad's generated `unconnected-(...)` names on the PCB. This changes net names only. PA0/PA1 retain
  their actual single-pin named copper nets and remain visible ERC findings.
- Original silkscreen strokes remain editable board graphics, including text
  outlines and connector outlines extending past the board edge. They are not
  recovered text fields attached to footprints. Native references on F.Fab move
  with components; source silk must be reviewed separately when components move.
- Original pour *design intent* cannot be recovered from Gerbers. The final
  composited copper is represented by native zones with filled contours,
  overlapping the same-net native tracks and pads. Moving a trace alone will
  leave its old copper shape in those contours. For a redesign, replace the
  affected recovered zones with deliberate pour boundaries and reroute; inspect
  after refill. Do not treat automatic zone refill as a fidelity-preserving step.
- Curves used in recovered polygons are tessellated with a 0.001 mm arc target.
  Native trace arcs remain arcs. Small numerical polygon differences are reported
  by comparison with KiCad's exported Gerbers.
- Pads use ordinary KiCad mask expansion and paste margin rules derived from
  the entire aperture. Source rounded mask-aperture corners can differ from
  KiCad's expanded rectangular mask corners. Extra non-pad openings remain
  native graphics. `mask-paste-comparison.json` quantifies the separate mask/paste
  differences; the copper tolerance claim does not apply to solder mask.
- Package bodies, courtyards, exact connector models, 3D models, materials,
  copper weight and a fabrication stackup are not established by these files.
  Board thickness is the **unverified 1.6 mm working default**. No manufacturing
  tolerances or electrical ratings are inferred from it.

## Specific source discrepancies

### Feeder V2

1. H1 is **pin 1 GND, pin 2 HOST_VIN, pin 3 PA5, pin 4 PA11**. HOST_VIN feeds the
   SS34 diode before the +5V net. This corrects the earlier audit's reversed
   power/ground description. It does not establish contact order on a newer board.
2. U1 pad 4 is an isolated copper tab in the probe data and Gerbers. The PNG
   appears to join that tab to VOUT. The recovered PCB/schematic preserve the
   exported isolated pad and explicitly mark the discrepancy. The schematic's
   tab label describes the regulator function; it is not a new copper connection.
3. The MCU heading omits its full family designation. F103 pin names are a
   provisional interpretation supported by the supplied STM32F1 C source and
   package layout, not proof of the installed MCU or firmware compatibility.
4. SW1 physical pads 3 and 4 are isolated in the CAM. Their mechanical/electrical
   function needs confirmation; the reconstruction labels them PAD3/PAD4 and
   does not silently join them to the switch's two routed contacts.
5. C16/C17 are taken as 100 uF polarized capacitors from the source drawing;
   passive values and exact fitted parts still require BOM/physical confirmation.
   Source PA0 and PA1 copper nets have only one component pin each.
6. The supplied board/drawing is the V2 reference. It has not been established
   as the board matching the packaged V3.1 firmware binary.

### Busbars

1. Both archives labelled N1–N8 and N9–N16 contain N9–N16 slot signal names and
   identical plotted geometry, drill coordinates and flying-probe data. See
   `busbar-archive-comparison.json`. Export times and unused aperture declarations
   differ. Preserve the source mapping until the intended N1–N8 design is obtained.
2. The eight source references N1...N8 are **component references**, not reliable
   absolute slot signal numbers. Each slot has pin 1 signal, pin 2 VCC, pin 3 GND.
3. Interconnect headers and mounting holes are absent from probe component rows.
   They were recovered from the drill/pad geometry and traced through both layers.
   `JREC1` is the left 2×12, 2 mm header; `JREC2` is the right header where present.
   Their numbering is **new**: viewed from the top, rows run top to bottom, odd
   numbers on the left and even numbers on the right. Confirm any mating cable's
   convention before using these numbers externally.
4. The N17–N24 archive has only the left interconnect header. Unconnected pads
   remain unconnected, including unused header pins. Five plated mounting holes
   are present per busbar; their annuli are not assigned to ground.
5. VCC is the source net name; these files do not establish its operating voltage,
   allowable feeder current, contact rating or the current V3 backplane pinout.

## Validation and reproducibility

Each `validation.json` reports native KiCad version, matched pads/drills,
coordinate errors, front/back copper area differences, ERC/DRC types, unrouted
items and schematic parity. All pad/net comparisons must pass. Hole comparisons
allow the sub-micron differences between copper-pad and Excellon centres.

The KiCad project retains a 0.2 mm default net-class clearance and normal default
edge/silk checks; basic minimum track/hole settings are in `.kicad_pro`. Those are
working review rules, not a recovered fabrication contract. Source copper reaches
closer to some edges and neighbours than those rules permit. No DRC exclusions
were added. Full native reports and intermediate Gerbers live in ignored
`build/kicad/`; the committed JSON summaries avoid local filesystem paths.

To reproduce the reference in a disposable checkout (this overwrites generated
hardware files), install KiCad 9 with its Python bindings and standard symbol
libraries, then the Python dependencies in `tools/kicad/requirements.txt`.
Make `pcbnew` importable in that Python environment and set `KICAD9_SYMBOL_DIR`
to the installed standard symbol directory. From the repository root (the tools write to the matching PCB folders):

```sh
python tools/kicad/build_boards.py
python tools/kicad/build_schematics.py
python tools/kicad/sync_isolated_nets.py
python tools/kicad/validate.py
python tools/kicad/compare_sources.py
python tools/kicad/render_previews.py
```

Before fabrication, establish the actual parts, stackup and connector numbering,
replace edited pours and resolve source discrepancies and DRC findings.

## Four-layer motherboard extension

See [motherboard project](../../Microsmt-PNPv3/PCB_motherboard/docs/KICAD_RECOVERY.md) for the independent generator,
source normalization, functional schematic and known interpretation limits. The
motherboard uses all four copper layers when tracing plated-hole connectivity.
Source custom-pad region geometry is cached as physical millimetre polygons;
Gerber aperture macros are not reconstructed from pickled unit objects. The
33 near-circular slot paths are retained, and via-in-pad copper asymmetry is
preserved by the recovered zones. Its local library is MicroSMT_Motherboard,
so generating it does not prune the feeder/busbar library.

## Controller and V485 board generator

`tools/kicad/recover_remaining.py` reconstructs the V3 controller, V485
controller, 480 mm busbar, three short-busbar variants, display and feeder. Their
native files are in each board’s `KiCad/`, their evidence is in `docs/` and new
JPG previews are in `photos/`. Short-busbar variants have separate project/library
names and prefixed reports in the shared board folder.

Manufacturing data supplies pad numbers/nets, not a complete device-symbol model.
The new schematics therefore use generic passive pins, with values from supplied
BOMs. Unspecified values and inferred hole references remain explicit. Back-side
SMDs and non-plated mechanical holes retain their source side/type. Duplicate
probe rows are collapsed only after physical/net agreement checks.

Rotated rectangle macros are converted from their true corners. Gerbonara’s
bounding-rectangle conversion falsely joins the V485 feeder’s 45-degree crystal
pads; the recovery code corrects that conversion and includes a runnable geometry
check. Original Gerbers are unchanged. Copper is compared after native KiCad
replotting, rather than judging correctness from a preview.

Use the Python interpreter matching your installed `pcbnew` bindings. Install
`tools/kicad/requirements.txt`; it selects Gerbonara 1.5 for Python 3.11 and
1.6.3 for Python 3.12+. The segment conversion handles both versions. From
the repository root:

```sh
python tools/kicad/recover_remaining.py --self-check
python tools/kicad/recover_remaining.py --validate v485_feeder
python tools/kicad/recover_remaining.py --render v485_feeder
```

Validation normalises generated global/NC net names and BOM flags in the reference
PCB before comparing it; use a reference copy, not an unreviewed redesign.

Run without a mode to build the named board(s), or omit names for all eight.
Generation refuses to overwrite an existing PCB. Regenerate only in a disposable
checkout after removing the selected generated project files; preserve manual
CAD edits. Use the listed generator for each project; their project lists are separate.
