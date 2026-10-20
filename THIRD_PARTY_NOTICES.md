# Third-party notices

This repository is an independent reorganisation prepared with ChatGPT assistance. The original MicroSMT designs and supplied files remain credited to their authors. See [CREDITS.md](CREDITS.md) for sources, local base revisions and changes.

## MicroSMT Bing-feeder

Original repository: [microsmt/Bing-feeder](https://github.com/microsmt/Bing-feeder).

The supplied [MIT license](Bing-feeder/LICENSE), copyright (c) 2025 microsmt, is retained with the collection. Its terms and attribution continue to apply to the upstream material.

## MicroSMT Microsmt-PNPv3

Original repository: [microsmt/Microsmt-PNPv3](https://github.com/microsmt/Microsmt-PNPv3).

The supplied README describes the project as open source. No root LICENSE file is present in the local source copy. This repository does not assign a replacement license to that material. The recovered motherboard in `Microsmt-PNPv3/PCB_motherboard/KiCad/` derives from the same collection. Clarify redistribution permission for both before publishing them.

## Recovered hardware and KiCad libraries

Feeder, controller and busbar references derive from Bing-feeder CAM and
schematics under its MIT license. The motherboard derives from Microsmt-PNPv3
and retains that collection’s unresolved licensing terms. Recovery scripts,
inferred connector references and technical notes are local additions.

Standard symbols were copied from KiCad libraries 9.0.2, copyright 2025
[KiCad Community](https://gitlab.com/kicad/libraries/kicad-symbols). They remain
in project-local libraries and schematic caches; inherited symbols were flattened.
These definitions retain **CC-BY-SA 4.0 with the KiCad electronic-design exception**.
The [full license and exception](Bing-feeder/V3-feeder/PCB_feeder/KiCad/libraries/LICENSE.KiCad-symbols.txt)
remain beside the copied symbols. Recovery-specific regulator, switch and
motor-driver definitions are local additions documented in the
[recovery notes](tools/kicad/RECOVERY_NOTES.md). No license change to the original
designs is implied.

## Firmware build dependencies

The [combined V485 PlatformIO project](Bing-feeder/V485-feeder/CODE_feeder/README.md) downloads the ST STM32 platform, STM32CubeF1 HAL/CMSIS and GNU Arm toolchain through PlatformIO. They are external build dependencies, not copied source trees in this repository; their own copyright and license notices apply. The application remains derived from MicroSMT's supplied Bing-feeder firmware.

The project also retains a modified [STM32F103C8 linker script](Bing-feeder/V485-feeder/CODE_feeder/stm32f103c8.ld), based on `tool-ldscripts-ststm32` 0.3.0's `stm32f1/STM32F103C8TX_FLASH.ld`. Both application and bootloader linker layouts derive from that script. Its source notice identifies STMicroelectronics copyright (c) 2021 and BSD-3-Clause licensing; the notice and full license terms are retained in that file. Local changes mark flash startup pointer tables read-only and split flash into separate loader/application regions, with a fixed application identity section. Both scripts retain the full source notice/license.

## Local additions

The file organisation, generated previews, additional STL exports, README galleries and build notes are local additions prepared with ChatGPT assistance. No new repository-wide license has been selected. These notes do not change any upstream copyright or license.
