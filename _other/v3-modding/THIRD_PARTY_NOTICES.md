# Third-party material

## Bing feeder

The Bing-feeder source was originally imported from
<https://github.com/microsmt/Bing-feeder> at
`a76d544a318b353734c67b3bd35c459c58e7aeee`.

The upstream MIT license, copyright (c) 2025 microsmt, is preserved verbatim in
[../../Bing-feeder/LICENSE](../../Bing-feeder/LICENSE).

## MicroSMT PNPv3

The Microsmt-PNPv3 source was originally imported from
<https://github.com/microsmt/Microsmt-PNPv3> at
`1eab7b5d22e8095ea566c91d089b629b6995c82e`.

Its README describes the project as open source, but this imported repository
has no root LICENSE file. We have not assigned a replacement license to that
material. Clarify its applicable terms before redistribution.

Canonical source material now lives in the `../../Bing-feeder/` and `../../Microsmt-PNPv3/` source directories; duplicate imports were removed.

## New work

The code in `firmware/`, tests and tools were written for this project.
The feeder core is a new implementation of the documented cycle contract;
vendor source was inspected but not copied into that core.

A license for new project contributions has not yet been selected. This notice
does not change the terms of any upstream material.

## Recovered hardware and KiCad library symbols

The feeder and busbar references derive from Bing-feeder CAM and schematics
under its MIT license. The recovered motherboard derives from Microsmt-PNPv3
files and shares that collection's unresolved licensing terms; it is not covered
by Bing-feeder's MIT license. Recovery scripts, inferred connector references
and technical notes are project additions.

Standard symbol definitions were copied from KiCad libraries 9.0.2, copyright
2025 KiCad Community: <https://gitlab.com/kicad/libraries/kicad-symbols>. They are
in `hardware/libraries/MicroSMT_Recovered.kicad_sym` and the schematic caches.
Inherited symbols were flattened; names are cached in a project-local library.
These definitions retain **CC-BY-SA 4.0 with the KiCad electronic-design
exception**. The full license and exception are preserved in
[hardware/libraries/LICENSE.KiCad-symbols.txt](hardware/libraries/LICENSE.KiCad-symbols.txt).
The symbol library also includes new recovery-specific regulator, switch and
motor-driver definitions; their source and purpose are recorded in the recovery
notes. No license change to the upstream designs is implied.

## Build dependencies

PlatformIO downloads ARM CMSIS, STM32F1 device/startup support, Raspberry Pi Pico
SDK, TinyUSB and toolchains into its package directory. These are not copied into
the reference source tree; their original license and copyright files remain in the downloaded
packages. Any distribution of linked firmware must account for those notices.
Versions and platform pins are recorded in `platformio.ini` and the
[build validation](docs/firmware-build-validation.md). Pico SDK integration uses
[the community PlatformIO platform](https://github.com/maxgerhardt/platform-raspberrypi/tree/5d4561a05e3b212660ac6fdd3fbfb328d1988aa1).
No OpenPnP source was copied into the bench protocol implementation.
