# Firmware build validation

Validation date: 2026-09-21. Build and simulation evidence only; no serial device
was opened, no image was uploaded, and no physical acceptance was performed.

## Tooling

- PlatformIO Core 6.1.19.
- ST STM32 platform 20.0.0; CMSIS 5.5.1 and STM32F1 device package 4.3.5.
- STM32 ARM GCC package 1.70201.0 (GCC 7.2.1).
- Pico platform commit `5d4561a05e3b212660ac6fdd3fbfb328d1988aa1`.
- Pico SDK package 1.20200.0 at `4315984000afe20ac82c78c597a3c4a591f524b0`.
- Pico ARM GCC package 1.90301.200702 (GCC 9.3.1).
- PlatformIO native platform 1.2.1.

Dependencies were installed into an isolated temporary PlatformIO Core directory.
The existing user package directory was not changed. Builds use CMSIS and Pico
SDK directly. Upstream Pico SDK PIO headers emit unsigned-comparison warnings;
these warnings were not suppressed or treated as application validation.

## Checks passed

```sh
pio run -e feeder_f103_bench -e bridge_pico2 -e bridge_pico2w -e native
python3 tools/check.py
make check
make arm-check
```

- All four PlatformIO environments built successfully.
- Eight feed-cycle behavior scenarios and seven bus test groups passed.
- Bus tests cover all 256 UART byte values, CRC single-bit mutations, framing,
  collision, overflow, timing faults, parser resynchronization and simulated
  request/reply exchanges. FEED remains inhibited on repeated requests.
- Five Python packet-client tests passed, including a shared C/Python golden frame.
- AddressSanitizer and UndefinedBehaviorSanitizer host runs passed; LeakSanitizer
  is disabled because the runner uses ptrace (the tested C core has no heap).
- Cortex-M3 portable core object compilation passed separately.

## Local image fingerprints

Generated binaries remain ignored under `.pio/`; they are not committed.
These hashes identify this validation build, not guaranteed reproducibility
across host paths, toolchain changes or build timestamps.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `.pio/build/feeder_f103_bench/firmware.elf` | 138000 | `d04df2b991ed1109b731081b40a63a9243d658be5b076838d312b04bd94f0355` |
| `.pio/build/feeder_f103_bench/firmware.bin` | 2768 | `76bd2a17ea14ab1feba4091d44b4a1ef5f22f868504d41baf69ac3fb8d96835a` |
| `.pio/build/bridge_pico2/firmware.elf` | 78488 | `2a5421aa115b4979bdb1fa1dda8cde942a033edbc7d84cb326daeb038c9ef5b4` |
| `.pio/build/bridge_pico2/firmware.uf2` | 63488 | `e137b4773f11c3307bcf27facc6928f4f2d01b381db968ce7d0075bbd9641c9e` |
| `.pio/build/bridge_pico2w/firmware.elf` | 78492 | `1e89ef8795ee1b88bfcff0043e57036dc20df9f2d0ef4708f88b93f1b24acfb8` |
| `.pio/build/bridge_pico2w/firmware.uf2` | 63488 | `068bd21f95b4a3aa5ae154e15acc432f662d4fe7dc316b9c7c23bd5cb9ccbe7a` |

The Pico 2 W fingerprints above are the default build with no Wi-Fi credentials;
Wi-Fi is disabled until local configuration is supplied. A separate link check
with non-secret placeholder credentials exercised the radio/TCP code: 52,468 bytes
RAM and 314,240 bytes flash. That configuration was removed and the default image
rebuilt afterward. No image was flashed and no real network credentials were used.

## Controller extension checks

- Shared USB/TCP controller: seven host test groups cover readable commands,
  bounded scans (including address 247), malformed input, cancellation/disconnect,
  timer rollover, link/queue faults, wrong/late replies and the diagnostic-only gate.
- Wi-Fi adapter: the actual C adapter was compiled against SDK/lwIP fakes to test
  fragmented input, single-client ownership, USB takeover, replacement sessions,
  output backpressure, buffer overflow, disconnect/error callbacks, idle timeout
  and join pacing. This is not a real lwIP/radio integration test.
- Five Python client tests cover packet integrity/correlation and fragmented TCP
  replies, errors and no-retry behavior. No socket or serial device was opened.
- `make check`, `make arm-check`, all four PlatformIO builds and `tools/check.py`
  passed. The controller core also compiles with strict warnings for Cortex-M3;
  actual Pico 2/Pico 2 W target images use the RP2350 toolchain.
- Sanitizers passed for the portable core and Wi-Fi adapter mocks. Vendor snapshots
  and archives remain unchanged.

## Limits

No claim is made about actual MCU identity, oscillator tolerance, electrical
levels, motor stopping, optical indexing, contact reliability, USB timing,
multi-node loading or OpenPnP operation. Wireless integration is compiled and callback-tested only; real Wi-Fi load may
interfere with the software sampler. Those limits require the hardware acceptance
work in [the bench guide](feeder-bus-bench.md). The feeder image is deliberately
a diagnostic target, not production motion firmware.
