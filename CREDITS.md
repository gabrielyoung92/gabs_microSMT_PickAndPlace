# Credits and changes

## Original projects: MicroSMT

The supplied machine and feeder designs, original firmware, PCB fabrication files, assembly manuals and reference images come from **MicroSMT and the contributors to its original repositories**. Their authors retain credit for that work.

| Collection here | Original repository | Last checked-out upstream commit in the local source copy |
| --- | --- | --- |
| [Bing-feeder](Bing-feeder/README.md) | [microsmt/Bing-feeder](https://github.com/microsmt/Bing-feeder) | `4e7bf9590ed011ffd1ef305c69eb399adfa82c80` |
| [Microsmt-PNPv3](Microsmt-PNPv3/README.md) | [microsmt/Microsmt-PNPv3](https://github.com/microsmt/Microsmt-PNPv3) | `99dd6f8608cd8dbeea67fb241e4b944d8da39b83` |

These commit IDs identify the local repositories' checked-out base revisions. The collections had already been extracted, renamed and supplemented locally before this consolidation, so they are reorganised working copies rather than exact exports of those commits. No fresh upstream sync was performed for this move.

The original repository links are the place to check for current official files, support and updates. Existing vendor introductions and support links remain in each collection's README. This collection is independent and does not imply MicroSMT endorsement.

## Local changes with ChatGPT assistance

File organisation, conversions, previews, documentation and local firmware changes were prepared with **ChatGPT assistance**. The original MicroSMT work remains credited above.

Changes made to the local collections include:

- Extracting and regrouping files into clearly named feeder, controller, machine and PCB folders.
- Adding missing matching STL exports from supplied STEP models while retaining the STEP files.
- Adding JPG previews: the original model preview plus eight isometric views, and top/bottom/isometric PCB views derived from Gerbers.
- Grouping images in `photos/` directories and adding linked README galleries and navigation.
- Renaming Arduino text sources to `.ino`, grouping sketches correctly, and placing STM32 C variants in separate source folders with build notes. Renaming did not change the firmware source contents.
- Porting the ESP32-C3 controller to PlatformIO C++ with `main.cpp` and `config.h`. See its [changelog](Bing-feeder/V485-Feeder%20Controller/CODE_esp32C3/CHANGELOG.md).
- Combining V485 feeder variants into shared C/H modules, with separate bootloader/application builds and an addressed RS485 updater. See its [changelog](Bing-feeder/V485-feeder/CODE_feeder/CHANGELOG.md) and [update guide](Bing-feeder/V485-feeder/CODE_feeder/BOOTLOADER.md). Physical hardware validation remains outstanding.
- Packaging loose Gerber sets into ZIP files after checking their contents.
- Reconstructing editable KiCad references for all 13 Gerber sets, with local libraries, source evidence, native connectivity/CAM checks and linked previews. These are local reconstructions of MicroSMT designs, not supplied original KiCad projects.
- Grouping shared recovery tools in [tools/kicad/](tools/kicad/README.md) and machine setup records in [Microsmt-PNPv3/docs/](Microsmt-PNPv3/docs/README.md).

Previews, conversions and generated documentation are convenience additions. A render, renamed source file or successful software check does not establish physical compatibility, a complete vendor firmware build or a tested fabrication release.

## KiCad reconstruction

Recovered KiCad references sit beside the matching PCB Gerbers, with supporting reports in `docs/`. Recovery tools, inferred connector references and technical notes are local additions; the recovered hardware remains derived from MicroSMT’s original material. See [third-party notices](THIRD_PARTY_NOTICES.md) for KiCad library attribution.

## Licensing

The supplied [Bing-feeder MIT license](Bing-feeder/LICENSE) is retained. The local Microsmt-PNPv3 source copy has no root LICENSE file; no replacement license has been applied to it. No new repository-wide license has been selected, and this reorganisation does not change upstream terms. See [third-party notices](THIRD_PARTY_NOTICES.md).
