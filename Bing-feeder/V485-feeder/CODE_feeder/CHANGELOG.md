# V485 feeder development changelog

Original firmware: [MicroSMT / Bing-feeder](https://github.com/microsmt/Bing-feeder). Local adaptations were prepared with ChatGPT assistance; upstream authors retain credit.

## 0.1.1 — Initial bus validation

- New 8 mm defaults: reversed feed, normal peel, NC and two sensor events per
  item (4 mm). Blank options use the saved width's direction default; missing or
  invalid counts use the width's default. Valid custom EEPROM profiles survive.
  SWD and RS485 commissioning explicitly install these profiles. Wider units keep
  normal/normal/NC with one event (4 mm).

- JOG advances/retracts whole items using the saved event count per item. Temporary
  reversal preserves EEPROM motor direction. Peel is held off through jogs and
  idle gaps until normal feeding/reset. Correlated STATUS and existing watchdogs
  remain in use. One request carries the complete item count; 32-bit counters
  support up to 10,000 events, with a 3-second no-progress guard and a total bound
  of 2 seconds + 1 second/event. The client follows that bound and never resends
  motion after lost ACKs. STOP disables both motors with a latched E4; Ctrl+C sends it.
- --pitch-mm converts item spacing to exact sensor counts, rejecting unresolvable
  pitches. Tape width, sensor spacing and component pocket pitch remain distinct.
  Reverse/backlash/optical-edge positioning still needs physical validation.

- Direct UID-targeted SETCOUNT saves default optical events (1–99) without a menu.
  The configuration CLI accepts --count; two events on the 8 mm type means nominal
  4 mm for manual/F0 feeds. Explicit F commands retain event-count semantics.

- Independent EEPROM feed/peel reversal and NC/NO peel-switch polarity. Default
  profiles are width-specific as above; existing blank extension bytes need
  no commissioning write. Shared universal loader/image format 3 remains compatible.
- CONFIG/SETCONFIG read and save options using addressed CRC packets, hardware UID,
  boolean validation and no menu/button requirement. Only bus ID reassignment
  requires menu 01. Settings stop idle peeling while saving and reject active feeds; verified writes
  commit a versioned record last. Invalid/torn records latch E3 with direct serial
  recovery; repair requires a power cycle before motors are eligible again.
- Direction applies to each motor's run outputs only; brake, opto counting, request
  correlation and debounce remain intact. Ordinary feed/peel limits remain
  10 seconds; item moves use separate progress and scaled total bounds. NO means an open
  input requests peeling, including a disconnected switch.
- tools/configure_unit.py reads or saves and verifies settings, including a lost
  save acknowledgement without replay. SWD commissioning initializes explicit defaults.
  ESP32 bridge source forwards the two new settings commands.
- Offline checks cover every combination, reload persistence, actual drive GPIOs,
  both contact levels, corruption/recovery, direct bus saves without arming, wrong UID, malformed values,
  EEPROM failure and the client. RS485 upload/image CRC and direct settings save/readback have been verified on one
  board without menu selection; motor behaviour with the new settings remains pending.

## 0.1.0 — Unreleased

All work so far belongs to the initial development version. One 8 mm feeder has been programmed; application startup, flashing 00 and read-only RS485 identity/metadata/diagnostics have been confirmed. Physical motor/switch operation remains untested. Build and simulation results are software evidence only; development passes are not separate releases.

### Universal commissioning

- One common bootloader/application (image format 3), with checked EEPROM width 8/12/16/24 at byte 2. Unconfigured types inhibit both motors. Menu 05 and locally armed UID-targeted SETTYPE configure it; TYPE reports width/count/nominal step. The 8 mm wheel is nominally 2 mm/event and wider wheels 4 mm/event from owner-supplied 30-tooth, 60/30-hole geometry. F retains original event-count semantics.
- LOCATE flashes ID and LED without feeding; identity queries remain read-only.
- ST-Link-only commissioning programs and verifies both images, EEPROM boot record/ID/type and real startup without RS485 or buttons. The optional RS485 commissioning tool installs the common loader, uploads over RS485, verifies saved type/ID/UID and records the example 30-unit profile. A local menu 01 selection authorises remote settings; only one commissioning board is connected.
- Universal images require the universal loader; old width-specific images are rejected.

### Current implementation

- Direct USB host support: DIAG snapshots and an immutable-until-reset MONITOR token expose sensor movement and state without EEPROM writes. Report every PA3 edge, including manual/partial movement. Keep stock estimates on the PC and independent of motion acceptance. Distinguish application E1 index, E2 peel and E3 settings faults.

- Use 115200 baud for the RS485 bus, including both feeder applications, bootloaders, controller UART, uploader and ID-assignment tool. Keep reply delays, polling intervals and deadlines unchanged.

- Operating IDs are 1–99. EEPROM ID FF is saved as unassigned 0, which flashes 00 and blocks both motors and manual/serial feeds. Local/remote assignment cannot save 0; reserved transport address 0 remains available for programming and update recovery. The controller rejects N0, while F0 still selects the saved feed count.

- PB6 is now a pull-up input for the isolated NC peel-tension switch, replacing the unused external feed trigger and its EXTI handler. Both original buttons stay installed: PA4 short tap feeds; PA2 hold/release selects remote ID, update, local ID or default-count editing, and PA2 edits/saves values. Startup holds, overlapping button presses and PA4 presses begun in menus cannot become delayed feeds. Edits save only on a two-second PA2 hold/release, or cancel after 20 seconds. Menus stop both motors and reject feeds.
- SysTick stops peeling on an open switch, debounces restart and enforces a separate continuous-peel deadline. Startup and both bootloader variants keep both motors stopped. SWD remains enabled.
- Locally armed IDENT/SETID commands and tools/assign_id.py support remote ID changes through the ESP32 bridge. Check responding destination IDs, target the MCU UID, verify EEPROM before changing ID, and confirm the same UID at the new ID without retrying a save after a lost ACK.

- One shared STM32 HAL/PlatformIO project for 8 mm and 12/16/24 mm feeders, with pinned framework/toolchain, explicit clock/GPIO setup and runtime width selection. Allow tension-controlled idle peeling on wider feeders; 8 mm peels only during feeds.
- Atomic feed reservation/start/stop, complete-line UART framing, bounded parsing, deferred display updates and a SysTick motor deadline. Invalid input cannot become a truncated movement request. Faults stop both motors and latch until reset.
- Checked EEPROM reads and verified writes for saved ID/count. Communication failures never manufacture ID 0. Failed setting writes/readback inhibit operation under an uncertain saved ID. Shared button scanning and nonblocking feedback keep serial processing available.
- Addressed, CRC-protected FEED requests with session/sequence tokens. Read-only STATUS polls return RUNNING, DONE, FAULT or UNKNOWN for the retained request. DONE follows the final sensor event and index-motor idle outputs; ISRs never transmit. Subsequent manual feeds do not overwrite a completed addressed result.
- Pair with the matching local 0.1.0 controller development build for M600 completion ACKs. F counts sensor events; F0 uses the positive saved default. Send movement once; only status reads may be retried. Legacy direct-adapter N/F commands retain acceptance-only OK/Busy replies.
- Separate 8 KB SWD-installed bootloader and 56 KB application. Addressed updates preserve feeder ID/count, check width/layout/vectors/tag and CRC, bound erase/programming to the application region, and commit EEPROM validity last. Interrupted uploads remain in recovery; no A/B rollback.
- Python uploader supports explicit IDs, sequential batches, retry-safe BEGIN/DATA, lost-completion confirmation and offline image inspection. Shared drivers, linker scripts and newlib hooks retain the supplied attribution/license notices.

### Software checks

The universal application and bootloader build without compiler/linker warnings. Native address/undefined-behaviour checks cover both variants, motor/count races, startup, UART damage/overflow, settings faults, button timing, retained completion, deadlines and tick wrap. Actual controller/feeder sources linked together pass simulated normal completion, lost replies and a jam. Loader/uploader simulations cover flash bounds, metadata failure points, retry/restart, stale replies and image rejection.

Physical feed/indexing, PB6 switch response, loaded bus timing and power-loss recovery on real boards remain untested.

### Original sources

Both original files are retained in this repository's initial Git revision; active application sources are now in `src/`.

| Imported source | Vendor identification | Original SHA-256 |
| --- | --- | --- |
| `V485_feeder_8mm.c` | Banner 8 mm V26; Version line V25 | `701c5520c1e80cf2becc244e8f141f8ddb13eaa4589eea2d2843b60acacd016c` |
| `V485_feeder_12-16-24mm.c` | V26 | `ea91d10dae360ab89fbda77119278508f6ac475cafa857af218f58722153b55e` |

0.1.0 identifies this unreleased local development work, independently of MicroSMT's vendor version labels. The separate V3 feeder programs have not been converted.
