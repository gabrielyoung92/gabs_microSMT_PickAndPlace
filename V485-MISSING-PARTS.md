# V485 missing parts

V485 file gaps for 8/12/16/24 mm feeders. Vendor file trees were rechecked on
**30 October 2026** with no changes. Original designs belong to MicroSMT; see [credits](CREDITS.md).

Source-to-local mappings are in the [import manifest](Bing-feeder/upstream-2026-10-21.json)
and [update notes](Bing-feeder/UPSTREAM-2026-10-21.md). The
[current comparison](Bing-feeder/UPSTREAM-2026-10-25.md) covers the supplied 16 mm slot.

## Confirmed file gaps

- [ ] **8 mm eight-position feeder slot STEP:** the [printable STL](Bing-feeder/V485-feeder/3D_parts_8mm/V485_3D_feeder-slot-8-position.stl) exists, but no editable STEP is supplied.

## Available

- [x] **16 mm one-position magnetic slot:** present in the vendor ZIP and
  [16 mm gallery](Bing-feeder/V485-feeder/3D_parts_16mm/README.md), with matching
  STEP, STL and nine previews.

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

V3 parts are a different design; check fit before substituting them.

When new files arrive, check their intended width/design, add matching STEP/STL and gallery links, then tick the relevant item above.
