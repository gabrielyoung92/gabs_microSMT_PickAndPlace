# V485 missing parts

Checked **22 October 2026** against MicroSMT's **21 October 2026 V485 CAD archive**, covering 8, 12, 16 and 24 mm feeders. Original designs belong to MicroSMT; see [credits](CREDITS.md).

All **64 source CAD entries** match their local destinations byte-for-byte, including entries consolidated into shared parts. These gaps are in the supplied archive, not files lost during extraction. See the [import manifest](Bing-feeder/upstream-2026-10-21.json) and [update notes](Bing-feeder/UPSTREAM-2026-10-21.md).

## Confirmed file gaps

- [ ] **8 mm eight-position feeder slot STEP:** the [printable STL](Bing-feeder/V485-feeder/3D_parts_8mm/V485_3D_feeder-slot-8-position.stl) exists, but no editable STEP is supplied.

## Received separately

- [x] **16 mm one-position magnetic feeder slot:** received on 22 October 2026 as `V485-16mm feeder slot(Magnetic)-1bit.STEP`. Added to the [16 mm gallery](Bing-feeder/V485-feeder/3D_parts_16mm/README.md) with the original STEP contents, a matching STL and nine previews. This file was not part of the 21 October archive.

## Needs clarification from Bing

These are differences between the supplied width sets, not confirmed missing requirements.

- [ ] **8 mm three-position feeder slot:** no STEP or STL supplied, although a [three-position holder](Bing-feeder/V485-feeder/3D_parts_8mm/V485_3D_feeder-holder-3-position.step) is supplied. Confirm whether a separate three-position slot is intended.
- [ ] **12/16/24 mm spring-support plate, sprocket cover and spool hook:** separate models are supplied only for 8 mm. Confirm whether the wider designs reuse these, incorporate their function elsewhere, or need additional files.
- [ ] **12/16/24 mm multi-position mounts:** no three/eight-position holders or slots are supplied for the wider widths. Confirm availability if multi-position mounts are wanted.

## Already present

- Bodies, tape covers, PCB covers, triggers, gears, gear brackets and motor supports for all four widths.
- One-position holders for all four widths.
- The **16/24 mm trigger cover** is in the [shared-parts folder](Bing-feeder/V485-feeder/3D_parts_shared/README.md); it is not missing.
- Common wider-feeder gears and worm are also in that shared folder.
- Every other supplied model has both STEP and STL locally.

V3 files are a different design and are not established substitutes for missing V485 parts. File availability alone does not establish physical fit.

When new files arrive, check their intended width/design, add matching STEP/STL and gallery links, then tick the relevant item above.
