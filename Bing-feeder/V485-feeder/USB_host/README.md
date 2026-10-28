# MicroSMT machine and feeder host

A small PC service for the [MicroSMT V485 feeders](../README.md), using a direct USB-to-RS485 adapter. OpenPnP connects over local TCP; the service owns the serial port, waits for the feeder to finish each advance, and keeps a basic stock estimate.

Original feeder designs and firmware belong to [MicroSMT](https://github.com/microsmt/Bing-feeder). This host and the local firmware changes were prepared by Gab with ChatGPT assistance. See [credits](../../../CREDITS.md).

**Version 0.1.0 is development software.** Offline checks exercise the real STM32 C sources and the host's TCP/HTTP paths, but this web-console change has not been tested against a real feeder or adapter. The demo uses simulated modules. The dashboard has been checked in a browser against the simulated bus; this does not establish physical feeder operation.

```text
OpenPnP 2.6 ── TCP 127.0.0.1:5001 ── PC service
                                         │
LAN feeder page ──── HTTP port 80 ────────┤
                                         │ USB–RS485, 115200 8N1
                                         └── STM32 feeders
```

The service supports feeders and an optional USB motion-controller connection (`--motion-serial`). The ESP32 project remains available for its existing standalone controller path; this service expects a **direct auto-direction adapter**, not the ESP32's filtered USB bridge.

## Try it without hardware

Use Python 3.10 or newer. From this folder:

```sh
python host_service.py --demo --ids 0-2
```

Open **http://COMPUTER-HOSTNAME/** (or `http://127.0.0.1/` on that computer). The motion controller and modules 0, 1 and 2 are simulated; 0 is unassigned, cannot advance, and is pre-armed for a demonstration ID assignment. Demo mode opens no hardware port, cannot flash firmware, and uses a separate `~/.v485/demo-stock.sqlite3` database by default.

If either port is occupied, select another pair:

```sh
python host_service.py --demo --ids 0-2 --tcp-port 15501 --web-port 15502 --motion-port 15503
```

The page is then at `http://127.0.0.1:15502`; OpenPnP would use TCP port 15501. Press Ctrl+C to stop. A first run without hardware can show the page and stock controls; physical button selection is still required for ID assignment on real feeders.

## Connect the adapter

Reference adapter: Waveshare CH343G **USB TO RS485 (B)**, associated with Amazon ASIN B0B8DWLT1V. Confirm the received model and terminal labels rather than relying on the ASIN alone. [Waveshare's specifications](https://www.waveshare.com/usb-to-rs485-b.htm) list hardware automatic direction control, A+/B-/GND and 300 baud–3 Mbaud. The host uses **115200, 8N1**, with no RTS direction switching.

Use the feeder bus's RS485 A, B and reference ground, retaining the existing feeder power supply. This USB adapter is a communications connection; it does not replace the feeder power supply. Check polarity and bus termination against the received adapter and busbar. Its manufacturer lists an onboard 120-ohm termination resistor; count the existing terminations before adding any. The manufacturer's node/loading guidance also needs checking against the actual bus population.

Install dependencies, then run on the PC which runs OpenPnP:

```sh
python -m pip install -r requirements.txt

# Windows: use the adapter's actual COM port and your feeder IDs.
python host_service.py --serial COM5 --ids 1-24

# Linux: prefer a stable /dev/serial/by-id/... name where available.
python host_service.py --serial /dev/ttyACM0 --ids 1,2,7
```

The web page defaults to **0.0.0.0:80**, reachable on the LAN by hostname or IPv4 address, using plain HTTP with no authentication. The OpenPnP feeder TCP listener remains **127.0.0.1:5001**. One OpenPnP TCP client is allowed at a time. The adapter is opened exclusively where supported. Close other serial monitors, uploaders and ID tools; the daemon is the sole RS485 master. Use its local page for uploads and ID assignment while it is running.

The STM32 applications, bootloaders and adapter must all use 115200. Install the matching [local bootloader and application](../CODE_feeder/BOOTLOADER.md) first. Stock vendor firmware does not implement this protocol. A previously installed 9600-baud loader needs replacing over SWD. Nothing in this folder installs, flashes or enables a service automatically.

## HTTP port 80 and hostname access

Defaults are `--web-host 0.0.0.0 --web-port 80`. Browse to
`http://machine-hostname/` or `http://machine-hostname.local/` when the service runs on a machine
with the corresponding hostname and the client can resolve it. A LAN IPv4 address also works.
The service does not configure DNS/mDNS, router forwarding or an existing web
server. Another service already using port 80 must be accounted for first.

Override the web bind/port when needed, for example:

```sh
python host_service.py --demo --ids 0-2 --web-host 127.0.0.1 --web-port 15502
```

On Linux systems that restrict ports below 1024, grant the service
`CAP_NET_BIND_SERVICE` through its systemd unit (`AmbientCapabilities=` and
`CapabilityBoundingSet=`). Keep the service running as the serial-port user's
account. There is no need to run the whole bridge as root or change permissions
on the system Python executable. Startup installation is separate from the
software's bind/port settings.

## OpenPnP 2.6

Use a separate **regular GcodeDriver** for feeder actuators, with a TCP connection to `127.0.0.1`, port `5001` (or your chosen port). This driver has no machine-motion axes. No machine profile was edited by this work.

| Setting | Value |
| --- | --- |
| Actuator double command | `M600 N{IntegerValue} F0` |
| Actuator value | Feeder ID, 1–99 |
| Confirmation regex | `^ok(?:\s.*)?$` |
| Error regex | `(?i)^error:.*$` |
| Command timeout | At least 20,000 ms |

`F0` uses the feeder's saved positive advance count. A fixed count also works, e.g. `M600 N{IntegerValue} F4`. F counts index-sensor events, not millimetres. Leave unrelated connect, home, enable, disable and positioning commands empty for this feeder-only driver.

The service sends FEED **once**, checks matching session/sequence STATUS replies, and returns `ok N7 F4` only after DONE. Lost acceptance/status replies cause status reads, never an automatic second advance. BUSY, FAULT, UNKNOWN and deadlines return `error:`. A broken connection is not permission to resend; inspect an unknown movement outcome. There is no automatic motion replay after a service restart.

Use the synchronous GcodeDriver. An asynchronous driver needs its own completion handling; a delayed `ok` alone does not make an asynchronous actuator wait. Optional `M115` returns the host identity and `M400` confirms an idle bus; neither is needed for normal synchronous feeder actuation. Other G-code is rejected.

## Stock is informational

On the page, enter a reel label, the number of parts **remaining now**, pulses per component pocket and a low-stock threshold. Saving takes a fresh movement baseline. A count of zero is allowed.

- Movement comes from the actual PA3 sensor total, including manual advances, powered hand movement and partial feeds. It is not inferred from how many commands the PC sent.
- Divide measured pulses by pulses per part. Fractional usage is retained for partial pocket movement; remaining stock is clamped at zero while used stock continues increasing.
- Low, zero, unknown or uncertain stock **never blocks feeding**. Inventory/telemetry failures after a confirmed feed do not turn DONE into a feed failure. Genuine motor faults, invalid ID 0 and maintenance still inhibit advances as before.
- A feeder's hardware UID owns its reel record. Changing its bus ID keeps that record; replacing a module at the same ID does not inherit another module's stock.
- The MCU's monitor token stays in RAM through PC/service restarts. It resets with the MCU. The host then preserves known usage, counts movement seen since that boot, and marks the estimate **uncertain** because movement just before reset may have been lost. Reload/correct stock to acknowledge a fresh baseline.
- A temporary disconnect can be reconciled from the same runtime token and counter. While offline, the displayed estimate is stale. Unpowered tape movement, missed sensor edges, empty pockets and failed picks are not measured as usable parts. The sensor has no direction information: reverse hand movement also adds usage, so correct the estimate after reversing/unloading tape.

Real stock lives in `~/.v485/stock.sqlite3`; on Windows `~` means the current user's home. Override with `--database PATH`. Back up that file with the service stopped. No inventory is stored in Git, and there are no EEPROM writes for movement counting or monitor tokens. If the database cannot be opened, startup logs the error and uses clearly labelled temporary inventory so feeding remains available.

The sensor counter is 32-bit. A single wrap is reconciled; an ambiguous gap of at least half the counter range is marked uncertain. Never treat this as an audited component inventory.

## Diagnostics, IDs and updates

The page shows each module's assigned ID, width, default count, runtime state, switch contact, commanded peel output and last communication error. Select a feeder ID for its UID and raw sensor total. Sensor/output status does not prove that tape or a motor physically moved correctly.

The firmware display now distinguishes:

| Display | Meaning |
| --- | --- |
| Flashing `00` | Unassigned ID; neither motor may run |
| `E1` | Index feed deadline exceeded |
| `E2` | Continuous peel deadline exceeded |
| `E3` | Application settings read/write failure or invalid saved setting |

The bootloader's existing error display/protocol remains separate. Runtime motor/settings faults still require inspection and reset or an allowed update path; stock controls do not clear them.

Enable **maintenance** before changing IDs or uploading firmware. It rejects new PC advances immediately; an already accepted feed may finish. The page waits for bus ownership before doing maintenance work. Manual/external controls on other modules remain local MCU inputs—stop the machine before physical setup.

For an ID change, select feeder menu **01** and submit the current and requested ID from the page. IDs 1–99 are valid; address 0 is reserved for programming one unassigned module at a time. The existing assignment tool checks responding destination IDs, targets the MCU UID, saves once and verifies at the new ID. It cannot detect an unplugged/offline device using that ID.

For updates, select the module ID and matching application `firmware.bin`. Image checks precede BOOT/erasure; the maintained addressed updater performs the transfer and CRC verification under exclusive bus ownership. Maintenance stays enabled after success or failure. Recover a failed upload before leaving it. A loader cannot be replaced through this update path.

## Feeder console

The page refreshes cached telemetry every second. Select a feeder ID for its MCU
UID, width, index switch, peel motor, local menu mode and movement total. Selection
fills the reel, diagnostic, ID assignment and firmware target controls. Filter by
ID, width, reel label or UID. The summary shows discovered feeders, ready modules,
fault/read errors and low stock estimates. Missing or stale telemetry is visible;
maintenance pauses background polling and labels readings as cached. A lost host
connection disables actions and marks displayed data as cached.

Expand **Polling and diagnostics** and use **Read now** to read the installed
application size and CRC32. Firmware does not currently expose a release version;
the console uses image size/CRC to identify it. These metadata reads are explicit,
so normal polling does not add updater traffic to the bus.

Select an application file in **Firmware update** to check its vectors, universal
V485 tag, memory layout and size before upload. Its size and CRC appear beside the
file. Enable maintenance to unlock **Upload and verify**. Progress reports
connecting, erasing, transferring and verifying, with the final result retained
for the service session, including after a page reload. A busy bus rejects an
update immediately; it does not queue another flash. Maintenance remains enabled
after either success or failure. Demo mode supports image inspection but refuses
flashing. Results and firmware metadata are session-local; stock remains in SQLite.

## HTTP interface

The page uses the same local API available to other PC tools:

| Request | Body / purpose |
| --- | --- |
| `GET /api/status` | Cached modules, stock, errors and maintenance state; no serial action |
| `POST /api/maintenance` | JSON `{"enabled":true}` or false |
| `POST /api/polling` | JSON `{"ids":"0,1-24"}` |
| `POST /api/refresh` | JSON `{"address":7}`; read identity/diagnostics and installed image metadata |
| `POST /api/stock` | JSON `{"address":7,"label":"10k","quantity":3000,"pulses_per_part":4,"low":50}` |
| `POST /api/assign` | JSON `{"address":0,"new_id":7}`; maintenance and physical menu 01 required |
| `POST /api/image` | Raw application bytes; offline validation returns variant, size and CRC32 without touching the bus |
| `POST /api/update?address=7` | Raw application bytes, `Content-Type: application/octet-stream`; maintenance required |

JSON POSTs require `Content-Type: application/json`. Browser POSTs must come from the same hostname/IP and HTTP port as the page; omitted port 80 is accepted. This allows hostname and LAN access without authentication or TLS. No raw packet injection endpoint is provided. Advance commands use the dedicated TCP connection.

Polling reads one configured address per interval, default 0.25 seconds, and skips while another bus operation owns the port. Missing nodes consume a bounded reply timeout. Use the IDs actually present to keep the display responsive. Feed operations have bounded bus acquisition and take priority over subsequent background polls. After adapter disconnection, restart the service once the port is available again; automatic serial reconnection is not implemented.

For startup, use Windows Task Scheduler to run this command at login, or the prepared systemd service below on Debian. Use absolute script/database paths and the same account which can access the adapter. Start the host before OpenPnP. No startup task or service has been installed here.

## Check without hardware

```sh
python check_host.py
python ../CODE_feeder/tools/check_feeder.py
python ../CODE_feeder/tools/rs485_upload.py --self-check
python ../CODE_feeder/tools/assign_id.py --self-check
```

The host check needs Python and native `gcc`. It creates temporary databases/listeners and compiles the actual STM32 application with the existing temporary HAL substitutes. It exercises serial-to-TCP completion for both widths, lost/stale replies and adapter echoes, single-send movement, zero/uncertain stock, partial usage, host/MCU resets, UID-based ID changes, HTTP validation and maintenance. No hardware port or real stock database is opened. The checks also cover image inspection without serial traffic, firmware metadata, upload progress/results, demo flash rejection and failure recovery state. Browser checks use only simulated feeders and a temporary inventory database.

## Validation record — 29 October 2026

- Passed `python3 check_host.py`: real TCP/HTTP/SQLite paths, actual STM32 C
  harness, upload progress including a lost final acknowledgement, image checks,
  metadata reads, demo flash rejection, failure state and busy-bus rejection.
- Passed `ASAN_OPTIONS=detect_leaks=0 python3 ../CODE_feeder/tools/check_feeder.py`
  (leak detection is unsupported under the sandbox tracer; address/undefined
  behaviour checks remain enabled).
- Passed uploader and ID-assignment `--self-check` commands, Python compilation
  and JavaScript syntax checking.
- Browser verified feeder selection, installed image metadata, maintenance state
  and reel saving using simulated modules and a temporary database only.
- No hardware serial port opened, feeders moved, firmware flashed, startup service
  installed, machine profile changed, or repository commit/push performed.

### Port-80 follow-up — 29 October 2026

The CLI now defaults to LAN HTTP on port 80 and accepts same-origin browser
operations through hostname/IP URLs, including implicit `:80`. Regression
checks cover hostname case, LAN IPs, explicit ports and unrelated origins.
The development workstation is separate from the Debian 13 machine computer.
Installation and physical acceptance remain separate steps; this repository
contains generic setup instructions rather than local host inventory.

## Motion control and OpenPnP relay

```text
Browser ── HTTP :80 ── host service
                         ├── TCP 127.0.0.1:5001 ← OpenPnP feeder driver
                         │     └── USB–RS485 → feeders
                         └── TCP 127.0.0.1:5003 ← OpenPnP motion driver
                               └── USB → existing Smoothieware controller
```

Start with both serial devices specified, using the actual persistent paths:

```sh
python3 host_service.py --serial /dev/serial/by-id/RS485_ADAPTER \
  --motion-serial /dev/serial/by-id/SMOOTHIE_CONTROLLER --ids 1-30
```

Omit `--motion-serial` to retain feeder-only operation. Demo mode provides both
simulators and refuses `--motion-serial` so it cannot accidentally open real
motion hardware. Default ports are HTTP 80, feeder TCP 5001, motion TCP 5003.
The TCP listeners remain on loopback for OpenPnP on the same machine.

After closing OpenPnP and backing up its actual profile, change only the existing
motion driver's communication transport from serial to TCP `127.0.0.1:5003`.
Keep GcodeAsyncDriver, axis configuration, command blocks and response regexes.
The service opens the motion port at 115200 8N1 with DTR/RTS false. During normal
OpenPnP operation it forwards bytes and controller replies without rewriting them, adding background polls,
acknowledging on the controller's behalf, resetting, reconnecting, or retrying.
Only one motion TCP client can own that connection.

To use manual controls, disconnect the OpenPnP motion driver, then select
**Take manual control**. The service waits for `M400`, sets millimetres and
absolute mode, and reads machine coordinates without moving. Web ownership
blocks OpenPnP connections until **Return to OpenPnP**, which waits for motion
to finish before releasing the controller. A concurrent manual request is
rejected rather than queued. Manual mode is shared across browser tabs; it is
an operator mode, not a login or authentication system.

Available controls are XYZ jogs, A/B nozzle rotation, XYZ homing, motor enable,
outputs-off/motor-disable, pump, both nozzle valves, both camera lights,
position/endstop reads and a software halt. Home through the web interface once
per manual session before jogging. Confirm heads level or N2 below N1 before
each home: this machine's Z gate searches toward the centre from one side only.
Z+ raises N1 and lowers N2; both heads move whenever Z is jogged.

XYZ jogs use fresh `M114.2` machine coordinates and `G53 G1` targets, bounded to
X 0–385, Y 0–470 and Z −30–+30 mm. Steps are at most 10 mm; speed limits are
100 mm/s XY and 10 mm/s Z. These limits come from the earlier measured machine
and must be checked against the target machine before physical use.
Rotary steps are at most 90 degrees and 60 degrees/s. The exact firmware applies
G92 offsets to A/B even under G53, so rotary jogs instead use a fresh M114 work
angle and an absolute G1. Homing sets A/B work zero without physically rotating.
Every jog waits for M400 before reporting completion; G1's acknowledgement alone
is not treated as completed movement.

The display labels coordinates by source and age. During normal OpenPnP operation it observes existing reports only. The explicit
connected-jog/report controls below perform private requests and publish a
work-position report; there is no background telemetry injection.
Motor/output indicators are accepted command state, not measured motor power,
vacuum, pickup success or actual lamp state. Job, board and placement progress
are not available from this controller stream.

**Software halt** sends the verified USB real-time Ctrl-X byte, including while
a web operation or OpenPnP session is active. It terminates the TCP session and
invalidates motion/output confidence. It is not a physical emergency stop and
cannot act if the PC, browser/network or USB connection is unavailable. After a
halt, timeout, reset banner, serial failure, or disconnect with unresolved/partial
commands, inspect the machine and restart/recover deliberately. The service
never replays an ambiguous move or automatically clears the controller's halt.
A clean TCP disconnect can return to manual mode; accepted queued movement is
completed by M400 before the manual claim finishes.

The command semantics were checked against the documented controller revision:
[Robot.cpp](https://github.com/markmaker/Smoothieware/blob/23a1f0db/src/modules/robot/Robot.cpp),
[GcodeDispatch.cpp](https://github.com/markmaker/Smoothieware/blob/23a1f0db/src/modules/communication/GcodeDispatch.cpp),
[USBSerial.cpp](https://github.com/markmaker/Smoothieware/blob/23a1f0db/src/libs/USBDevice/USBSerial/USBSerial.cpp).
The target controller's actual firmware identity still needs checking at installation.

### Motion HTTP API

`GET /api/status` includes a `motion` object with ownership, busy/fault state,
coordinate source/time, endstops, command-derived outputs, recent serial lines,
bounds and the local TCP port. It does not send serial commands.

`POST /api/motion` accepts JSON with `action`:

| Action | Additional fields |
| --- | --- |
| `claim`, `release`, `read`, `enable`, `disable`, `all_off`, `halt` | None |
| `home` | `"heads_ready": true` after checking physical head orientation |
| `jog` | `"axis":"X", "distance":1, "speed":10` (mm/s or degrees/s) |
| `output` | `"name":"pump", "enabled":true` |

Output names are `pump`, `n1_valve`, `n2_valve`, `top_light`, `bottom_light`.
Standalone commands except claim and software halt require manual ownership.
The explicit connected test actions below reserve the controller briefly while
the existing TCP connection stays open.

### Debian 13 installation, when ready

This is preparation only; no host or OpenPnP configuration was changed.

1. Copy `USB_host/` and sibling `CODE_feeder/tools/` to a directory structure
   such as `/opt/microsmt/V485-feeder/`, preserving their relative paths.
2. Install Python 3 and pyserial (Debian's `python3-serial` package supplies it).
   Identify the two devices in `/dev/serial/by-id/`. Close serial monitors and
   disconnect OpenPnP before the host opens the controller.
3. Install [microsmt-host.service.example](microsmt-host.service.example) with
   mode 0644 at `/etc/systemd/system/microsmt-host.service`. Replace `YOUR_LOGIN` and both
   device placeholders, and adjust the feeder ID list and paths if necessary.
   The unit grants port-80 binding to this service and serial group access while
   running under the selected user. It does not modify the Python executable.
4. Run `sudo systemctl daemon-reload`, then `sudo systemctl start microsmt-host`.
   Inspect `journalctl -u microsmt-host`. Do not replace another port-80 service.
5. Open `http://MACHINE-HOSTNAME/` (or its LAN IP). Verify device identity, limits,
   controller firmware, head orientation and output mapping before actual motion.
   Switch the backed-up OpenPnP motion driver to local TCP port 5003 and verify
   its connection. Enable the service at boot with `sudo systemctl enable
   microsmt-host` after acceptance. Automatic process restart is intentionally
   off so uncertain operations are not hidden by a service restart.

### Motion validation — 29 October 2026

`python3 check_motion.py` checks actual TCP/HTTP paths against the offline peer:
fragmented byte-exact relay, a 100-command pipeline, unchanged replies, ownership exclusion, XYZ bounds,
nonzero A/B offsets, delayed M400 completion, output mappings, concurrent request
rejection, Ctrl-X interruption, lost acknowledgements, serial errors controller reset banners and partial
OpenPnP disconnects. `python3 check_host.py` covers the existing feeder paths and
full demo startup/shutdown with the optional motion simulator. Python compilation
and JavaScript syntax checks also passed.

Browser checks used simulated manual claim, homing, X jogging, A rotation and
camera-light control. No physical port was opened, no machine moved, no firmware
flashed, no service installed, and no OpenPnP profile changed on the machine computer.

Prepared systemd unit syntax passed `systemd-analyze verify`; the unit was not installed or started.

## Connected web jogging and unsolicited position reports — 29 October 2026

This is the owner-requested test path for leaving OpenPnP connected while jogging
from the browser. It is implemented and simulator-tested; actual OpenPnP DRO and
planner behaviour on the machine computer remain for the owner to verify.

1. Update the `USB_host` program on the machine computer and restart it; updating HTML alone
   does not update the running Python bridge. Connect OpenPnP's GcodeAsyncDriver
   to the motion TCP port (default 5003), enable and home in OpenPnP, then leave
   it idle with no running job or other queued/manual operation.
2. In the browser, tick **OpenPnP is enabled, homed and idle; no job is running**.
   This is an operator confirmation: the bridge cannot inspect OpenPnP's internal
   job state or command queue. Normal mm/absolute-mode configuration is required.
3. Use **Send position to OpenPnP** first. It does not move the machine. The page
   shows the exact report sent, its time and count, separately from whether
   OpenPnP has accepted it.
4. Select a small XYZ step and jog once. The same TCP connection stays open.
   The bridge waits for M400, checks current machine coordinates and bounds,
   performs the jog, waits for M400 again, then reads M114 in work coordinates.
   It sends one unsolicited line such as
   `C: X:101.0000 Y:50.0000 Z:0.0000 A:0.0000 B:0.0000` to OpenPnP.
5. Check OpenPnP's reported position/DRO and receive log. Do not resume a job
   until its coordinates agree with the controller. Repeat with one small move
   at a time if the initial report is accepted.

The normal five-axis POSITION_REPORT_REGEX from the machine command guide
accepts this report. The bridge removes M114's private leading `ok` so the line
is not mistaken for an acknowledgement of an OpenPnP command. All other private
M400, G21/G90, G1 and diagnostic replies are consumed by the bridge. Work/G92 and
rotary offsets are preserved in the published coordinates, rather than sending
machine coordinates into OpenPnP's work-coordinate state. Each operation returns
to ordinary OpenPnP relay mode automatically; no disconnection or manual release
is needed for a successful connected jog.

OpenPnP 2.6's [GcodeDriver.processPositionReport](https://github.com/openpnp/openpnp/blob/2.6/src/main/java/org/openpnp/machine/reference/driver/GcodeDriver.java)
parses unsolicited position reports and sets driver coordinates when its own
`motionPending` flag is false. It resets send-on-change state when coordinates
change. If it logs **Position report cannot be processed when motion might still
be pending**, it has not adopted that report as its new driver coordinates.
[Async location confirmation](https://github.com/openpnp/openpnp/wiki/GcodeAsyncDriver)
should be configured correctly; a sent report alone is not proof that the DRO,
planner and transformed head coordinates have updated. No OpenPnP code/profile
was changed or automatically patched for this test.

The bridge refuses a connected operation while serial commands/replies or a
partial command are outstanding. If OpenPnP sends any command during the brief
private operation, the bridge faults/closes that TCP session and rejects the
new command without queuing it to execute after the jog. It cannot safely mix
an independently planned move into a web move. Homing, motor and output controls
still use the standalone manual mode; connected mode adds jogging/reporting only.

Additional API actions for `POST /api/motion`:

| Action | Fields |
| --- | --- |
| `jog_connected` | `axis`, nonzero `distance`, optional `speed`, `idle_confirmed:true`, `homed_confirmed:true` |
| `report_connected` | `idle_confirmed:true`, `homed_confirmed:true` |

`GET /api/status` now includes `motion.openpnp_connected`, `position_report`
(text and sent_at), and `position_reports_sent`. These confirm transmission to
the TCP peer, not application-level acceptance. Simulator checks cover a live
TCP peer, one-byte fragmented replies, nonzero XYZ/A/B offsets, private-ack
isolation, continued relay after the report, idle/partial-command rejection and
concurrent-command failure. The existing standalone and async-pipeline tests
remain in `python3 check_motion.py`.

Browser verification of the connected path used a simulated OpenPnP TCP receiver:
report-only, X +1 mm and A +5 degrees produced exactly three unsolicited `C:`
lines on the same connection, without private `ok` replies. The page retained
its idle confirmation and displayed the last sent report/count. This verifies
the bridge/browser path, not an actual OpenPnP GUI or physical controller.
