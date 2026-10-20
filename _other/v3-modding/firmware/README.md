# VS Code / PlatformIO firmware

Open `MicroSMT.code-workspace` in VS Code and install the recommended PlatformIO
IDE extension. This opens the actual project root containing `platformio.ini`;
opening its parent directory does not select this project. No STM32Cube IDE,
CubeMX, HAL generation or Make installation is required for these builds.

In PlatformIO's **Project Tasks**, expand the desired environment and choose
**Build**. Alternatively, open **PlatformIO Core CLI** from the extension and run:

```sh
pio run -e feeder_f103_bench
pio run -e bridge_pico2
pio run -e bridge_pico2w
```

`pio run` builds the feeder and plain Pico 2 by default. The extension supplies
PlatformIO Core; a regular OS terminal may not have `pio` on its PATH. First
builds download the pinned platforms and their toolchains and require internet.

| Environment | Implementation | Output under `.pio/build/<environment>/` |
| --- | --- | --- |
| `feeder_f103_bench` | Plain C + CMSIS, candidate STM32F103C8 | `firmware.elf`, `firmware.bin` |
| `bridge_pico2` | Plain C + Pico SDK, RP2350 Pico 2 | `firmware.elf`, `firmware.uf2` |
| `bridge_pico2w` | Plain C + Pico SDK, RP2350 Pico 2 W | `firmware.elf`, `firmware.uf2` |
| `native` | Host behavior tests | `program` (or `program.exe`) |

The Pico builds use USB CDC and GP2. Pico 2 W additionally supports a diagnostic
Wi-Fi TCP endpoint when private credentials are configured; it defaults to USB
with Wi-Fi disabled. See [controller setup and commands](../docs/bridge-controller.md).
Pico SDK support comes from the pinned community PlatformIO platform in
`platformio.ini`; STM32 uses the official ST STM32 platform's CMSIS framework.

## What currently works in code

The bridge accepts a USB or configured Wi-Fi request, sends an addressed CRC-protected frame, and
returns only a matching feeder reply or a bounded error. The feeder implements
ping, status, raw inputs and silicon UID. Its FEED handler always returns
INHIBITED. Motor output latches remain low; sensor qualification and actual
motor control are not connected to the tested portable feed-cycle core.

This is a buildable communications bench implementation. The MCU selection and
pin map are candidates derived from the supplied V2 schematic. Do not interpret
successful compilation as confirmation that a purchased feeder matches it.
No hardware has been flashed or tested. Programming and recovery must be planned
against the actual board before using an Upload action.

Read [the bus and wiring guide](../docs/feeder-bus-bench.md) before assembling a
fixture. The stock busbar is not already an addressed shared bus.

## Host checks without Make

From the PlatformIO Core terminal, with Python 3 and a desktop C compiler:

```sh
python tools/check.py
```

On systems where Python 3 is named `python3`, use that command instead. Host tests
need a native GCC-compatible compiler; this is separate from the embedded
cross-compilers PlatformIO downloads automatically. The script runs C behavior tests and Python packet-client tests.
Existing `make check` and `make arm-check` remain available to CLI users.

Generate a diagnostic frame offline, without opening any hardware:

```sh
python tools/feeder_bus.py ping --address 1 --transaction 1
```

Later, with a verified and programmed bench fixture, install `pyserial` into
your Python environment and add `--port <serial-device>` to exchange one request.
For Wi-Fi use `--host <controller-address>` instead of `--port`. The client
supports `ping`, `status`, `inputs` and `uid`, and never automatically
retries. Close any serial monitor first. See [validation evidence](../docs/firmware-build-validation.md).
