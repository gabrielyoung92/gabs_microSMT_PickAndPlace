# V485 feeder development changelog

Original firmware: [MicroSMT / Bing-feeder](https://github.com/microsmt/Bing-feeder). Local adaptations were prepared with ChatGPT assistance; upstream authors retain credit.

## 0.1.0 — Unreleased

All work so far belongs to the initial development version. No physical feeder or controller has been programmed or tested with this firmware. Build and simulation results are software evidence only; development passes are not separate releases.

### Current implementation

- Operating IDs are 1–99. EEPROM ID FF is saved as unassigned 0, which flashes 00 and blocks both motors and manual/external/serial feeds. Local/remote assignment cannot save 0; reserved transport address 0 remains available for programming and update recovery. The controller rejects N0, while F0 still selects the saved feed count.

- PA2 is now a pull-up input for an isolated NC peel-tension switch. PA4 is the only control button: tap advances; hold/release selects remote ID, update, local ID or default-count editing. Edits save only on a two-second hold/release, or cancel after 20 seconds. Menus stop both motors and reject feeds.
- SysTick stops peeling on an open switch, debounces restart and enforces a separate continuous-peel deadline. Startup and both bootloader variants keep both motors stopped. SWD remains enabled.
- Locally armed IDENT/SETID commands and tools/assign_id.py support remote ID changes through the ESP32 bridge. Check responding destination IDs, target the MCU UID, verify EEPROM before changing ID, and confirm the same UID at the new ID without retrying a save after a lost ACK.

- One shared STM32 HAL/PlatformIO project for 8 mm and 12/16/24 mm feeders, with pinned framework/toolchain, explicit clock/GPIO setup and separate width environments. Allow tension-controlled idle peeling on wider feeders; 8 mm peels only during feeds.
- Atomic feed reservation/start/stop, complete-line UART framing, bounded parsing, deferred display updates and a SysTick motor deadline. Invalid input cannot become a truncated movement request. Faults stop both motors and latch until reset.
- Checked EEPROM reads and verified writes for saved ID/count. Communication failures never manufacture ID 0. Failed setting writes/readback inhibit operation under an uncertain saved ID. Shared button scanning and nonblocking feedback keep serial processing available.
- Addressed, CRC-protected FEED requests with session/sequence tokens. Read-only STATUS polls return RUNNING, DONE, FAULT or UNKNOWN for the retained request. DONE follows the final sensor event and index-motor idle outputs; ISRs never transmit. Subsequent manual/external feeds do not overwrite a completed addressed result.
- Pair with the matching local 0.1.0 controller development build for M600 completion ACKs. F counts sensor events; F0 uses the positive saved default. Send movement once; only status reads may be retried. Legacy direct-adapter N/F commands retain acceptance-only OK/Busy replies.
- Separate 8 KB SWD-installed bootloader and 56 KB application. Addressed updates preserve feeder ID/count, check width/layout/vectors/tag and CRC, bound erase/programming to the application region, and commit EEPROM validity last. Interrupted uploads remain in recovery; no A/B rollback.
- Python uploader supports explicit IDs, sequential batches, retry-safe BEGIN/DATA, lost-completion confirmation and offline image inspection. Shared drivers, linker scripts and newlib hooks retain the supplied attribution/license notices.

### Software checks

All four PlatformIO targets build without compiler/linker warnings. Native address/undefined-behaviour checks cover both variants, motor/count races, startup, UART damage/overflow, settings faults, button timing, retained completion, deadlines and tick wrap. Actual controller/feeder sources linked together pass simulated normal completion, lost replies and a jam. Loader/uploader simulations cover flash bounds, metadata failure points, retry/restart, stale replies and image rejection.

Hardware flashing, physical feed/indexing, bus timing and power-loss recovery on real boards remain untested.

### Original sources

Both original files are retained in this repository's initial Git revision; active application sources are now in `src/`.

| Imported source | Vendor identification | Original SHA-256 |
| --- | --- | --- |
| `V485_feeder_8mm.c` | Banner 8 mm V26; Version line V25 | `701c5520c1e80cf2becc244e8f141f8ddb13eaa4589eea2d2843b60acacd016c` |
| `V485_feeder_12-16-24mm.c` | V26 | `ea91d10dae360ab89fbda77119278508f6ac475cafa857af218f58722153b55e` |

0.1.0 identifies this unreleased local development work, independently of MicroSMT's vendor version labels. The separate V3 feeder programs have not been converted.
