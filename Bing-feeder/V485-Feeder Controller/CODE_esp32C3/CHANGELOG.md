# ESP32-C3 controller development changelog

Original firmware: [MicroSMT / Bing-feeder](https://github.com/microsmt/Bing-feeder), ESP32-C3 RS485 master V25. Local adaptations were prepared with ChatGPT assistance; upstream authors retain credit.

## 0.1.0 — Unreleased

All work so far belongs to the initial development version. No physical controller or feeder has been programmed or tested with this firmware. Build and simulation results are software evidence only; development passes are not separate releases.

### Current implementation

- PlatformIO C++ project using Arduino, pinned ESP32 packages, native USB console and the vendor RS485 wiring. Settings/version live in config.h; firmware logic lives in main.cpp.
- Bounded USB parsing accepts M600 N<id> F<count> or N<id> F<count>. Reject malformed, incomplete and overlong input. LED feedback and UART response waits remain bounded; transmitter direction is released after the final stop bit.
- Send each addressed, CRC-protected FEED once with a startup session and request sequence, then use read-only STATUS polls to obtain its retained result. Wrong feeder/session/sequence, damaged frames and bare legacy ACKs cannot confirm the command.
- Return USB ok N<id> F<count> only after matching DONE confirms the requested index count and index-motor idle output. Acceptance/running replies never produce success. Busy, fault, unknown outcome and completion timeout return error: without ok. Never automatically resend movement.
- Use the matching local 0.1.0 feeder development build implementing FEED/STATUS. F counts sensor events; F0 selects the feeder's saved default. The default total completion deadline is 12 seconds around the feeder's 10-second motor guard.
- Forward the local addressed updater's INFO/BOOT/HELLO/BEGIN/DATA/END and locally armed IDENT/SETID packets unchanged between USB and RS485. The PC uploader owns update retries and verification. Late feed results cannot activate the update interlock or swallow the loader's DONE reply. Block controller feeds until update/settings traffic has been idle for 10 seconds.
- Checked OpenPnP 2.6 ReferenceAutoFeeder/GcodeDriver command substitution and confirmation handling. Document M600 actuator templates, confirmation/error patterns and the synchronous/asynchronous distinction. No machine profile changes.

### Software checks

The ESP32 target builds successfully. Retained native address/undefined-behaviour checks cover uploader packets, fragmentation, CRC rejection, input recovery, update interlock, no early success, single advance, lost/stale replies, faults and deadline/sequence wrap. Actual controller/feeder sources linked together pass simulated normal completion, lost replies and a jam for both feeder widths. Extracted OpenPnP 2.6 Java confirmation/error methods pass an offline handshake check.

No hardware has been flashed or physically validated. 0.1.0 is an unreleased local development version, independent of MicroSMT's V25 identification.
