# Credits and changes

## Original projects: MicroSMT

The supplied machine and feeder designs, original firmware, PCB fabrication files, assembly manuals and reference images come from **MicroSMT and the contributors to its original repositories**. Their authors retain credit for that work.

| Collection here | Original repository | Last checked-out upstream commit in the local source copy |
| --- | --- | --- |
| [Bing-feeder](Bing-feeder/README.md) | [microsmt/Bing-feeder](https://github.com/microsmt/Bing-feeder) | `4e7bf9590ed011ffd1ef305c69eb399adfa82c80` |
| [Microsmt-PNPv3](Microsmt-PNPv3/README.md) | [microsmt/Microsmt-PNPv3](https://github.com/microsmt/Microsmt-PNPv3) | `99dd6f8608cd8dbeea67fb241e4b944d8da39b83` |

These are the consolidation base revisions. File names and folders were
reorganised locally; the tables do not describe exact upstream checkouts.

Use the vendor repositories for official files and support. This is an
independent machine project, not a MicroSMT release.

## 21 October 2026 feeder update

The V3 and V485 feeder archives were imported on 22 October 2026 from
[`microsmt/Bing-feeder` at `056f6109`](https://github.com/microsmt/Bing-feeder/commit/056f6109d805260af609c1af03ae064e5c2fcba4).
Identical archives are also published in
[`microsmt/Microsmt-PNPv3` at `c8b939c4`](https://github.com/microsmt/Microsmt-PNPv3/commit/c8b939c44d9ad02c62b70e846f31879f0561a1f8).
This feeder import retains the local firmware, electronics and additional models.
STEP originals, local STL exports and previews are distinguished in the manifest.
See the [update notes](Bing-feeder/UPSTREAM-2026-10-21.md) and
[source manifest](Bing-feeder/upstream-2026-10-21.json).

## Local changes with ChatGPT assistance

Gab prepared the local code, conversions and documentation with ChatGPT assistance:


- Extracting and regrouping files into clearly named feeder, controller, machine and PCB folders.
- Adding missing matching STL exports from supplied STEP models while retaining the STEP files.
- Adding JPG previews: the original model preview plus eight isometric views, and top/bottom/isometric PCB views derived from Gerbers.
- Grouping images in `photos/` directories and adding linked README galleries and navigation.
- Renaming Arduino text sources to `.ino`, grouping sketches correctly, and placing STM32 C variants in separate source folders with build notes. Renaming did not change the firmware source contents.
- Porting the ESP32-C3 controller to PlatformIO C++ with `main.cpp` and `config.h`, including sensor-completion M600 acknowledgements and USB-to-RS485 forwarding for the local addressed feeder updater. See its [changelog](Bing-feeder/V485-Feeder%20Controller/CODE_esp32C3/CHANGELOG.md).
- Adding the powered-feeder PC host: direct USB–RS485, local OpenPnP feeder TCP, port 80 dashboard, stock estimates, configuration, input tests, update queue and native part/package editing. Machine motion, cameras, pickup teaching, nozzle management and job execution remain in OpenPnP.
- Combining V485 feeder variants into shared C/H modules, with separate bootloader/application builds and an addressed RS485 updater. See its [changelog](Bing-feeder/V485-feeder/CODE_feeder/CHANGELOG.md) and [update guide](Bing-feeder/V485-feeder/CODE_feeder/BOOTLOADER.md). Application uploads and CRC verification have been checked on bench units; loaded tape and pickup acceptance remain machine-side tests.
- Packaging loose Gerber sets into ZIP files after checking their contents.
- Reconstructing editable KiCad references for all 13 Gerber sets, with local libraries, source evidence, native connectivity/CAM checks and linked previews. These are local reconstructions of MicroSMT designs, not supplied original KiCad projects.
- Grouping shared recovery tools in [tools/kicad/](tools/kicad/README.md) and machine setup records in [Microsmt-PNPv3/docs/](Microsmt-PNPv3/docs/README.md).

Build, geometry and bench checks are recorded in each project guide; renders
alone do not establish fit or electrical operation.

## KiCad reconstruction

KiCad files sit beside their source Gerbers, with evidence in `docs/`.
See [third-party notices](THIRD_PARTY_NOTICES.md) for the KiCad library licence.

## Licensing

The supplied [Bing-feeder MIT license](Bing-feeder/LICENSE) is retained. The local Microsmt-PNPv3 source copy has no root LICENSE file; no replacement license has been applied to it. No new repository-wide license has been selected, and this reorganisation does not change upstream terms. See [third-party notices](THIRD_PARTY_NOTICES.md).
