# USB to single-wire feeder bench bus

## Scope and electrical proposal

This is a custom bidirectional data wire **plus common ground**, not Dallas/Maxim
1-Wire. A future slot-ID EEPROM on PA11 is a separate investigation. The current
24-byte protocol is also not OpenPnP Photon: its transport was inspected, but
integration has not been implemented and this bridge cannot be configured as a
Photon feeder directly.

Proposed isolated, short-wire fixture, pending actual-board verification:

| Connection | Pico 2 / Pico 2 W | Candidate V2 feeder |
| --- | --- | --- |
| Bus data | GP2, physical pin 4 | PA5, H1 pin 3 |
| Reference ground | GND, physical pin 3 | H1 pin 1 |
| Bus pull-up supply | 3V3 OUT, physical pin 36 | Shared data pull-up only |
| Feeder power | Separate correctly rated supply | H1 pin 2; verify voltage/polarity |
| Slot identification | Not connected | PA11 / H1 pin 4 untouched |

Use one external pull-up, initially 2.2 kΩ to 3.3 V, and consider 100 Ω series
resistors at each data endpoint. These are bench starting values, not a qualified
bank design. Measure rise time, LOW voltage, current and overshoot before choosing
final values or cable length. Both drivers only sink LOW or release the line.
No pull-up to 5 V: candidate STM32 PA5 is not a 5 V tolerant input.

Do not power the feeder motors from Pico 3V3. Avoid driving an unpowered board
through its data pin. Confirm supply sequencing and ground routing. Disconnect
the stock Mega trigger driver before connecting the prototype; do not tie active
stock outputs together. The recovered busbars route separate slot trigger nets,
so converting them to a shared bus requires deliberate new routing or a reviewed
adapter, not simply plugging this bridge into the existing controller socket.

PA5 lacks a suitable hardware UART function on this candidate MCU. Both ends use
a shared timer-driven software UART at a nominal 9615 baud (104 µs/bit), 8N1,
with four samples per bit. RP2350 PIO is a possible future bridge improvement;
it is not used in this implementation. The firmware detects framing, overflow,
TX echo/collision and late sampling faults, releases the line and reports errors.
This is not multi-master arbitration. Use one master and unique node addresses.

RP2350 A2 has the documented E9 input leakage erratum (fixed in A3). This design
uses an external pull-up and active LOW drive rather than a weak pull-down, but
waveform verification on the actual Pico revision remains necessary.

## Bench protocol version 1

All frames are 24 bytes. Multi-byte integers and CRC are little endian.

| Byte(s) | Meaning |
| --- | --- |
| 0–1 | Sync A5 5A |
| 2 | Version 1 |
| 3 | Destination: feeder 1–247, host 0 |
| 4 | Source: host 0 in requests, feeder address in replies |
| 5 | Operation; reply sets bit 7 |
| 6–9 | 32-bit transaction correlation ID |
| 10–21 | 12-byte payload |
| 22–23 | CRC-16/CCITT-FALSE over bytes 0–21, init FFFF, polynomial 1021 |

| Operation | Request | Reply payload |
| --- | --- | --- |
| 01 PING | Arbitrary 12 bytes | Echo |
| 02 STATUS | Zeros | Byte 0 result, 1 state, 2 fault, 3 motion-enabled (always 0); 8–11 uptime ms |
| 03 INPUTS | Zeros | Byte 0 result; byte 1 raw bitmap: bit 0 PA3, bit 1 PA4, bit 2 PA5 |
| 04 UID | Zeros | Raw 96-bit silicon UID |
| 10 FEED | Reserved | Byte 0 INHIBITED (3), always |

Result 0 is OK; unsupported operations return 2. Unspecified reply payload bytes
are zero. Raw input levels do not establish active polarity or qualified index
events. The image defaults to feeder address 1 via `FEEDER_ADDRESS` in
`platformio.ini`; assign distinct addresses before connecting multiple nodes.
There is no broadcast, address discovery or persistent provisioning yet.

The transmitter waits at least two idle bit periods before starting. A frame
takes approximately 25 ms; the bridge bounds the whole request/reply attempt at
150 ms. The parser discards partial frames after a 10 ms inter-byte gap. Replies
must match CRC, source, destination, operation and transaction ID. IDs provide
correlation, not replay protection. Sessions and at-most-once motion handling
must be implemented before enabling motion or adding command retries.

## USB / optional Wi-Fi interface

USB CDC accepts ASCII lines terminated by LF (CR is ignored):

- `INFO`: bridge version, GPIO and nominal baud.
- `STATS`: cumulative framing, overflow, collision and timing fault counters.
- `HELP`: command list.
- `PING/STATUS/INPUTS/UID <address>`: readable diagnostics.
- `SCAN <first> <last>`: bounded UID scan; `ABORT` cancels an exchange/scan.
- `XFER <48 hexadecimal digits>`: one complete encoded diagnostic request frame (operations 01–04 only).

A matching response is `RX <48 hexadecimal digits>`. Failures include
`ERR REQUEST`, `ERR LINE_TOO_LONG`, `ERR BUSY`, `ERR LINK` and `ERR TIMEOUT`.
Only one transaction can be outstanding. Disconnecting the active USB/TCP
session cancels transmission and releases the bus. Pico 2 W can expose the same
commands on TCP 4242 with private Wi-Fi configuration; USB has exclusive priority.
See [controller setup](bridge-controller.md) for configuration, response formats,
network limits and tests. Both MCUs have watchdogs. No command is retried automatically.
An RX response proves only what that response states; it never implies tape motion.

## Remaining bench acceptance

1. Identify the feeder revision/MCU and record stock firmware recovery before programming.
2. Verify connector continuity, rails, PA5 loading, and motor-driver truth table.
   LOW latches are software intent, not electrical proof of stopped motors.
3. Initially isolate motor power and verify one-node ping/UID/status on a scope or
   logic analyzer, including reset, USB removal, missing peer and held-low faults.
4. Test two uniquely addressed nodes, then cable/contact loading and the full bank.
5. Establish measured sensor qualification and motor/peel sequencing, then implement
   motion authorization, replay protection and completion reporting before motion tests.

## References

- [Pico series documentation and pinouts](https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html)
- [RP2350 datasheet and E9 erratum](https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf)
- [Candidate STM32F103x8/xB datasheet](https://www.st.com/resource/en/datasheet/stm32f103c8.pdf)
- [PlatformIO CMSIS framework](https://docs.platformio.org/en/latest/frameworks/cmsis.html)
- [Pinned Pico SDK PlatformIO integration](https://github.com/maxgerhardt/platform-raspberrypi/tree/5d4561a05e3b212660ac6fdd3fbfb328d1988aa1)
- [OpenPnP Photon packet implementation inspected](https://github.com/openpnp/openpnp/blob/develop/src/main/java/org/openpnp/machine/photon/protocol/Packet.java)

The OpenPnP link tracks a moving branch and is research context, not a dependency.
