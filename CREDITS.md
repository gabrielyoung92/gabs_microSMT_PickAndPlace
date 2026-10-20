# Credits and changes

## Original projects: MicroSMT

The supplied machine and feeder designs, original firmware, PCB fabrication files, assembly manuals and reference images come from **MicroSMT and the contributors to its original repositories**. Their authors retain credit for that work.

| Collection here | Original repository | Last checked-out upstream commit in the local source copy |
| --- | --- | --- |
| [Bing-feeder](Bing-feeder/README.md) | [microsmt/Bing-feeder](https://github.com/microsmt/Bing-feeder) | `4e7bf9590ed011ffd1ef305c69eb399adfa82c80` |
| [Microsmt-PNPv3](Microsmt-PNPv3/README.md) | [microsmt/Microsmt-PNPv3](https://github.com/microsmt/Microsmt-PNPv3) | `99dd6f8608cd8dbeea67fb241e4b944d8da39b83` |

These commit IDs identify the local repositories' checked-out base revisions. The collections had already been extracted, renamed and supplemented locally before this consolidation, so they are reorganised working copies rather than exact exports of those commits. No fresh upstream sync was performed for this move.

The original repository links are the place to check for current official files, support and updates. Existing vendor introductions and support links remain in each collection's README. This collection is independent and does not imply MicroSMT endorsement.

## Reorganisation by Gab, with ChatGPT assistance

Gab directed the organisation of this library, with **ChatGPT assisting with file organisation, conversions, previews, documentation and verification**. Those additions do not make the original MicroSMT designs Gab's or ChatGPT's work.

Changes made to the local collections include:

- Extracting and regrouping files into clearly named feeder, controller, machine and PCB folders.
- Adding missing matching STL exports from supplied STEP models while retaining the STEP files.
- Adding JPG previews: the original model preview plus eight isometric views, and top/bottom/isometric PCB views derived from Gerbers.
- Grouping images in `photos/` directories and adding linked README galleries and navigation.
- Renaming Arduino text sources to `.ino`, grouping sketches correctly, and placing STM32 C variants in separate source folders with build notes. Renaming did not change the firmware source contents.
- Adapting the ESP32-C3 controller into a PlatformIO project with `src/main.cpp`, settings in `src/config.h`, a version string and a build guide. Local version 0.1.0 changes command validation, input/ACK framing, retry behavior and status messages while retaining the supplied GPIO and baud defaults. These are independent local changes; see its [changelog](Bing-feeder/V485-Feeder%20Controller/CODE_esp32C3/CHANGELOG.md).
- Combining the V485 8 mm and 12/16/24 mm firmware into one plain C PlatformIO / STM32 HAL project, split into board, feeder, RS485, EEPROM and display `.c`/`.h` modules with settings in `src/config.h`. Separate environments preserve the wider source's continuous peel-motor behaviour. Local versions 0.1.0–0.3.0 use current pinned framework/compiler packages, with explicit unsupported file-I/O hooks and a corrected ST-derived linker layout, atomic feed acceptance, a latched feed timeout and complete-line receive framing; I/O and EEPROM defaults are retained, while physical MCU/crystal assumptions and operation remain unverified. These are independent local changes; see its [changelog](Bing-feeder/V485-feeder/CODE_feeder/CHANGELOG.md).
- Adding a local V485 RS485 bootloader/update tool with destination-ID packets, shared peripheral drivers, EEPROM boot metadata and separate loader/application PlatformIO builds. Hardware installation remains unverified; see the [bootloader guide](Bing-feeder/V485-feeder/CODE_feeder/BOOTLOADER.md).
- Packaging loose Gerber sets into ZIP files after checking their contents.
- Moving the earlier custom V3 development project into [_other/v3-modding/](_other/v3-modding/README.md), and updating its paths to the two collections.

Previews, conversions and generated documentation are convenience additions. A render, renamed source file or successful software check does not establish physical compatibility, a complete vendor firmware build or a tested fabrication release.

## Earlier custom development

The V3 modding project contains Gab-directed custom firmware, tools, recovered KiCad references and technical notes. Those project additions are separate from the supplied MicroSMT sources; recovered hardware remains derived from the original source material. Its [existing notices](_other/v3-modding/THIRD_PARTY_NOTICES.md) describe the earlier imports and KiCad library attribution in more detail.

## Licensing

The supplied [Bing-feeder MIT license](Bing-feeder/LICENSE) is retained. The local Microsmt-PNPv3 source copy has no root LICENSE file; no replacement license has been applied to it. No new repository-wide license has been selected, and this reorganisation does not change upstream terms. See [third-party notices](THIRD_PARTY_NOTICES.md).
