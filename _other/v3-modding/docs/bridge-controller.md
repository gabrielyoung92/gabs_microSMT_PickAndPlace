# Pico 2 / Pico 2 W feeder controller

The controller is a diagnostic bench implementation. USB and Wi-Fi use the same
portable command handler. It runs the existing addressed feeder protocol, not
OpenPnP Photon and not a drop-in replacement for the stock Mega pulse driver.
The existing candidate STM32 image supplies UID, status and raw inputs; its
motor handler remains inhibited. The bridge additionally rejects all bus
operations except PING, STATUS, INPUTS and UID, including through raw XFER.

## Build and connection

- `pio run -e bridge_pico2`: USB-only Pico 2.
- `pio run -e bridge_pico2w`: Pico 2 W with optional Wi-Fi and USB fallback.
- Neither build flashes a device. Use the hardware verification/recovery steps
  in [the bench guide](feeder-bus-bench.md) before programming or wiring.

For Wi-Fi, copy `firmware/bridge/bridge_wifi_config.h.example` to the ignored
`.local/bridge_wifi_config.h` and fill in the SSID/password locally. Empty or
missing credentials disable Wi-Fi. The supported initial setup is 2.4 GHz,
WPA2-Personal, station mode with DHCP. Credentials are compiled into the UF2;
keep configured binaries private. There is no captive portal, saved runtime
configuration, access-point mode, OTA, HTTP UI, TLS or application authentication.
Use the diagnostic TCP endpoint only on a trusted bench LAN.

The firmware asynchronously joins/rejoins Wi-Fi and listens on TCP **4242** after
obtaining an address. Find its address in the router's DHCP lease table. It has no
mDNS hostname or USB network-status command yet. Radio initialization/join failure
leaves USB diagnostics available; a physical test must confirm actual recovery.

Only one TCP client is accepted. An open USB CDC session (DTR asserted) takes
priority: it disconnects/rejects TCP clients until the USB terminal closes. USB
power alone does not claim ownership. Disconnects, USB takeover, receive/output
buffer overflow, or 30 seconds without incoming TCP data close the network session
and cancel its pending bus exchange. Do not infer motor stopping from cancelling
a transport exchange: motion is absent from this build.

Each TCP client gets a different internal session ID. Partially received commands,
queued replies and ongoing scans are discarded on disconnect; they cannot resume
or leak into a replacement session. TCP callbacks only queue bytes. The main loop
owns the command handler and bus transactions. Output queues are bounded; a slow
client is disconnected rather than blocking bus processing indefinitely.

## Commands

ASCII lines, LF terminated; CR is ignored. Maximum command length is 63 characters.
Commands and address spelling are strict: uppercase commands, decimal addresses
1–247, one separating space, no trailing arguments. Overlong/invalid-character
lines are discarded through LF. The following INFO output is firmware capability,
not evidence that a physical feeder has passed acceptance.

```text
INFO
STATS
PING 1
STATUS 1
INPUTS 1
UID 1
SCAN 1 48
ABORT
```

- `INFO`: bridge v2, bus protocol v1, GPIO 2, nominal baud and inhibited motion.
- `STATS`: cumulative physical-link faults and current active/scan flags.
- `PING address`: echo check; `PING address=1 OK` after a matching valid reply.
- `STATUS address`: result, feed state/fault, motion capability and uptime.
- `INPUTS address`: raw bitmap; sensor polarity is not inferred.
- `UID address`: the feeder's 96-bit silicon UID as 24 hexadecimal digits.
- `SCAN first last`: one UID request per address, no broadcast or retries. Emits
  `SCAN BEGIN`, `NODE address=... uid=...` or `MISS address=... reason=TIMEOUT`, then
  `SCAN END found=... missing=... reason=COMPLETE`. Address range is inclusive.
- `ABORT`: releases the wire and clears partial reply state; terminates a scan
  with `reason=ABORT`, then emits `OK ABORT`. INFO/STATS/HELP/ABORT remain available
  while busy. Other commands return `ERR BUSY` without replacing active work.
- `XFER <48 hex digits>`: retained compatibility with the Python diagnostic client.
  Only operations 01–04 are accepted. Reply remains `RX <48 hex digits>`.

Requests/replies retain the CRC and address/operation/transaction correlation
checks from bus protocol v1. Typed commands allocate incrementing transaction IDs
within a boot; these are not persistent sessions or at-most-once motion protection.
Raw XFER callers supply their own IDs and must avoid reusing IDs for late replies.
Every exchange has a 150 ms deadline, including transmission. A scan advances on
an ordinary timeout, but stops on link faults or inability to queue a request.
Scanning 48 absent addresses takes approximately 7.2 seconds plus scheduling time.
There is no automatic command retransmission after a Wi-Fi reconnect.

A scan inventories responding *addresses*, not physical slots. All stock bench
images default to address 1, so assign distinct addresses before a multi-node test.
Multiple boards using one address cannot be reliably enumerated by this scan;
collision detection does not prove uniqueness. Persistent addressing, slot EEPROM
identity and motion replay protection remain future work.

## Host client

Offline encoding remains the default; these examples do not open a device:

```sh
python tools/feeder_bus.py uid --address 1
python tools/feeder_bus.py status --address 1 --transaction 123
```

After an explicitly authorized and validated fixture is available:

```sh
python tools/feeder_bus.py uid --address 1 --port <serial-device>
python tools/feeder_bus.py status --address 1 --host <controller-address>
```

`--tcp-port` defaults to 4242. TCP uses Python's standard library; USB needs
`pyserial`. The client performs one bounded exchange and does not retry. The TCP
client closes its connection after each reply; use a TCP terminal for SCAN output.

## Timing and validation boundary

Bus timing still uses the existing 26 microsecond interrupt sampler, not PIO.
Wireless interrupts and lwIP activity may delay it. Late ticks raise observable
link faults and release the wire; compilation and mocked callbacks do not prove
that this arrangement works under radio load. Scope tests under sustained Wi-Fi
traffic are required. PIO or a dedicated timing core is a candidate improvement
if measurements show unacceptable jitter; no claim of deterministic Wi-Fi timing
is made.

Host tests cover the shared command handler and the actual Wi-Fi adapter against
SDK/lwIP fakes: fragmented input, bounds, competing clients, USB takeover, stale
session isolation, output backpressure, disconnect/error callbacks, idle timeout
and rejoin pacing. Embedded builds check integration with the real pinned SDK.
No RF, TCP-on-device, GPIO or physical feeder acceptance has been performed.
