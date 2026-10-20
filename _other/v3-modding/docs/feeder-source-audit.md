# Initial feeder source audit

21 September 2026. Based on the imported local repositories, their archives and
the supplied schematic. These are document and source findings; they have not
been validated against a physical feeder.

## What was actually found

The missing individual feeder source was supplied as **C code in `.txt` files**,
now renamed to `.c` without changing their contents:

| Material | Project-relative path |
| --- | --- |
| Small feeder C source, 234 lines | `../../Bing-feeder/V3-feeder/CODE_feeder_8mm/V3_feeder_8mm_2mm-4mm-pitch.c` |
| Wider feeder C source, 312 lines | `../../Bing-feeder/V3-feeder/CODE_feeder_12-16-24mm/V3_feeder_12-16-24mm.c` |
| Feeder schematic | `../../Bing-feeder/V3-feeder/PCB_feeder/V3_feeder_schematic.png` |
| Feeder fabrication files | `../../Bing-feeder/V3-feeder/PCB_feeder/V3_feeder_gerber_2025-02-06.zip` |
| Feeder source folders | `../../Bing-feeder/V3-feeder/CODE_feeder_8mm/` and `../../Bing-feeder/V3-feeder/CODE_feeder_12-16-24mm/` |
| Mega bridge source | `../../Bing-feeder/V3-Feeder Controller/CODE_MEGA2560/mega2560_bingfeeder_48pin/mega2560_bingfeeder_48pin.ino` |
| Consolidated V3 reference files | `../../Bing-feeder/V3-feeder/` |

Both extracted C text files match their archive members byte-for-byte. Their
includes reference `stm32f10x.h` and `stm32f10x_iwdg.h`, and they use STM32 Standard
Peripheral Library calls. The inspected snapshots/ZIPs do not supply a complete
feeder build project with those libraries, startup/vector code, linker script or
clock configuration. Finding source is therefore not yet a reproducible build.

Each feeder source now has its own folder and `README.md`. Shared build
requirements are in `../../Bing-feeder/STM32-BUILD.txt`.

The Mega sketches are a separate Arduino AVR program; they are not the program
running inside each feeder. The main machine's LPC1769 motion firmware is another
separate target. Our new portable C core is independent of all three build trees.

## Revision and binary evidence

The schematic title is **bing feeder V2**, version V1.0, updated 2025-02-06.
The diagram's MCU heading says **STM32C8T6**, an incomplete family designation.
The STM32F1 headers, the wider source's STM32F103 comment and the package pinout
make **STM32F103C8T6 a candidate**, not a verified installed part number.

Both the Bing-feeder 2025-1208 and Microsmt-PNPv3 2026-0914 bundles contain
`bingfeeder-V3.1-8mm.hex`. All four already-extracted copies have the same SHA-256:

```text
9733f2ed5200b172e8a6fc575af54408fb4d1fb23809575d2a0c5a6784244b5d
```

Intel HEX record checksums passed. The records contain 2,292 data bytes at
`0x08000000..0x080008F3`; the initial vector words include stack pointer
`0x20000660` and reset vector `0x0800016D`.

This demonstrates that the differently dated bundles contain the same supplied
8 mm binary. It does **not** prove that either published C text file produces
that binary, nor does it identify the actual MCU, its capacity or the shipped
board revision. A future source/build comparison must establish that relationship.

## Preliminary pin map from the V2 schematic and source

Schematic reference: [feeder SCH.png](../../../Bing-feeder/V3-feeder/PCB_feeder/V3_feeder_schematic.png).

| Signal | Pin / circuit | Evidence and limit |
| --- | --- | --- |
| Host trigger | PA5; H1 pin 3 | Direct net in schematic; rising-edge EXTI5 in small source lines 99–107 |
| Additional host contact | PA11; H1 pin 4 | Direct net in schematic; not initialized/used in the two C text files |
| Host power / ground | H1 pin 2 VIN / pin 1 GND | Corrected against flying-probe data, copper and schematic; supply passes through D1 SS34; exact V3 routing unverified |
| Optical index input | PA3, CN1 | Sensor block labelled EE-SX672; input pull-up and rising-edge EXTI3 in source |
| Manual button | PA4, SW1 to ground | Input pull-up and rising-edge EXTI4; small/wide source behavior differs |
| Index motor controls | PA6 / PA7 | Source `Motor_Start` / `Motor_Stop`, lines 79–92; connected to U3 |
| Other motor controls | PA8 / PA12 | Source labels this N30; stops/restarts around small feeder index cycle |
| Status LED | PB5 | Active-low drive shown in schematic and source |
| Debug | H2: GND, SWCLK, SWDIO, 3.3 V | SWD header shown; recovery procedure not supplied here |
| Motor driver | U3 TC1508A | Schematic label; source comments mentioning L298N are not the schematic part |
| Logic supply / clock | AMS1117-3.3; 8 MHz crystal | Drawing only; actual installed parts and runtime clock not measured |

The small feeder source drives PA6 high / PA7 low to run, and both high to stop.
Do not infer a verified brake/coast truth table or physical motor polarity from
comments alone. The second motor starts at program startup (lines 158–160) and
is stopped/restarted by the interrupt sequence (lines 182–215). Preserve the
mechanical intent, but measure it before implementing a board adapter.

## What this changes about the bus investigation

The earlier three-contact assumption is incomplete for the supplied V2 schematic:
H1 has **four contacts**, including PA11. This may provide an option for a local
slot-ID connection, but only if it exists and is independently routed on the
actual feeder and backplane. No new board or connector has been selected.

For an STM32F103C8, ST's pin table assigns PA5 to GPIO/SPI1_SCK/ADC12_IN5, without
a USART data function; it also does not mark PA5 as a five-volt-tolerant FT pin.
Thus a PA5 data bus is not simply a hardware-UART setting, and a shared 5 V
pull-up must not be assumed suitable. PA11 is also not a USART TX/RX pin. These
are conditional device constraints until the exact MCU is confirmed.
[ST STM32F103x8/xB datasheet, pin definitions](https://www.st.com/resource/en/datasheet/stm32f103c8.pdf).

Possible paths to investigate:

| Option | Required investigation |
| --- | --- |
| Open-drain single-wire on existing trigger contact | GPIO/timer receive/transmit design, electrical protection, pull-up voltage, bus capacitance and loading; no proof of a zero-PCB-change solution yet |
| LIN physical layer | Transceiver power/logic requirements, connector routing, node loading and master interface; would add interface hardware |
| RS485 | Differential pair and transceivers, contact count and slot-ID wiring; would add interface hardware |

No USART initialization is present in the supplied feeder source, but that alone
does not establish access to usable USART pins on the assembled PCB. The fourth
contact could be useful for slot ID even if it cannot provide hardware serial.

## Source issues relevant to the rewrite

These findings describe the C text files; they are not a claim about faults
observed in the supplied V3.1 binary or in a physical machine.

1. **Blocking, uncalibrated delay loops.** `delay()` is an empty counted loop
   (small source lines 7–12), called inside interrupt handlers. Its timing depends
   on the compiler/optimization/clock and can disappear under optimization.
   A communicating feeder needs timer-based progression and short interrupt work.
2. **Index interrupt acknowledgement is incomplete.** The small source's
   `EXTI3_IRQHandler` (lines 198–215) does not clear the EXTI3 pending bit. The
   wider source clears it only in its counting branch, not the terminal stop
   branch. Other handlers clear it later. This needs correction in a rebuilt
   implementation and comparison with the actual binary.
3. **No bounded feed completion/fault protocol.** The main loop reloads the
   watchdog, but there is no per-feed deadline or communication status machine.
   A watchdog reload alone is not a jam detector. This motivated the new core.
4. **Flash address needs investigation.** The wider source, line 16, uses
   `0x08010100` as configuration storage and calls it the last page. A genuine
   STM32F103C8 has 64 KB documented flash, ending at `0x0800FFFF`; that address is
   outside that region. Confirm the full device and linker layout before
   implementing persistence. [ST product specification](https://www.st.com/en/microcontrollers-microprocessors/stm32f103c8).
5. **Initialization and parameter handling are incomplete.** The wider source
   reads flash directly into `a`, with no initial erased-value validation before
   use in the ISR. Its first count begins at `b=2` and subsequent cycles reset
   `b=1`; physical feed pitch cannot be deduced reliably without testing.
6. **Stock bridge acknowledgements are not physical completion.** The Mega
   sketch uses 115200 baud, `M610 S0/S1`, and `M600 N...`. It forces one pulse,
   drives the selected output low for 10 ms then high, and does not wait for
   feeder feedback. Its `F` parsing is commented out. Null/bounds checks around
   the `N` parser and index are missing. Keep these as reference behavior only.

## What we can implement now

The first portable core in [firmware/feeder/](../firmware/feeder/) starts a bounded
feed cycle, rejects replacement while busy, counts qualified indexing events,
and latches timeout/abort faults. It has no GPIO or packet implementation and
does not reproduce the stock code's startup motion.

Before attaching transport, define transaction/session IDs and replay handling
so a retried FEED cannot advance tape twice. Before attaching hardware, establish
sensor qualification, motor/peel sequencing, watchdog behavior and measured
deadlines. A DONE report must remain tied to indexing evidence.

The next required vendor clarification is the target PCB/MCU revision, whether
H1's PA11 contact is exposed on the current backplane, and the matching buildable
source/programming procedure for the supplied V3.1 binary.

## Verification completed

- 372 imported files: unchanged SHA-256 hashes before/after relocation.
- 17 on-disk ZIP files: 514 entries including nested ZIP contents read with CRC
  verification; generated inventory at `build/archive-inventory.json`.
- Both C text files: exact matches to source archive members.
- Four extracted V3.1 HEX copies: identical hashes and valid record checksums.
- New core: eight host behavioral scenarios passed with AddressSanitizer and
  UndefinedBehaviorSanitizer. Leak detection is disabled because the task runner
  uses ptrace; the core has no heap allocation.
- New core: Cortex-M3 freestanding object compiled with strict warnings.

No stock source rebuild, target link, flashing, electrical test, bus test or
OpenPnP acceptance has been completed.

## Editable hardware recovery

Native KiCad projects for the V2 feeder and all three busbar archives are in
[hardware/](../hardware/README.md). The CAM test data establishes component
references, physical pad numbers and net names; reconstructed copper connectivity
adds the omitted busbar interconnect headers and mounting holes. See the
[recovery notes](../hardware/RECOVERY_NOTES.md) for the N1-N8 archive discrepancy,
isolated regulator tab and limits of the schematic/PCB reconstruction.
