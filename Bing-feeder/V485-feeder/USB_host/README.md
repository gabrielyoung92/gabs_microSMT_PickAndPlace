# Powered-feeder dashboard

The PC software for this MicroSMT PNPv3 machine. It owns the direct USB–RS485
adapter, manages the V485 feeders and gives OpenPnP a local TCP connection for
advancing them. The web page runs on plain HTTP port 80, without login or TLS.

Feeder designs and original firmware are by [MicroSMT](https://github.com/microsmt/Bing-feeder).
Local software was prepared by Gab with ChatGPT assistance. See [credits](../../../CREDITS.md).

## What runs where

```text
OpenPnP ── direct USB serial ── Smoothieboard motion controller
        ├─ USB cameras
        └─ TCP 127.0.0.1:5001 ── feeder host ── USB–RS485 ── V485 feeders
                                      │
Browser ── HTTP port 80 ───────────────┘
```

OpenPnP handles motion, cameras, pickup teaching, nozzle management, trays,
strip feeders and running jobs. The dashboard handles powered-feeder status,
configuration, firmware and estimated reel stock. Parts/packages can be edited
through the optional OpenPnP companion; they remain OpenPnP's own records.

## Source files

| File | Purpose |
| --- | --- |
| `host_service.py` | Serial bus owner, telemetry, feeder TCP and HTTP API |
| `dashboard.html` | All six web pages and popovers |
| `dashboard_tools.py` | Read-only remaining-job stock calculation |
| `OpenPnP-Web.py` | Runs inside OpenPnP for parts/packages, part assignment and reading job requirements |
| `bundle_firmware.py` | Packages the application build for web updates |
| `simulated_bus.py`, `check_*.py`, `check_firmware_ui.js` | Hardware-free checks |
| `microsmt-host.service.example` | Debian systemd service template |
| `../CODE_feeder/` | Feeder application, bootloader and serial tools |

Keep `USB_host` and its sibling `CODE_feeder/tools` together when copying the
software to the machine computer. Build products, stock databases and private
machine settings are not source files and stay out of Git.

## Run it

Python 3.10+ and pyserial are required for the real adapter. On Debian 13:

```sh
sudo apt install python3 python3-serial
```

For another Python environment, install `requirements.txt` using its package
manager or a virtual environment. From `USB_host`, a hardware-free demo is:

```sh
python3 host_service.py --demo --ids 0-2 --web-port 8080 --tcp-port 15501
```

Open `http://localhost:8080/`. Demo mode uses simulated units and a separate
stock database; it cannot flash feeders or change a real OpenPnP configuration.

For the machine, select the actual RS485 adapter and polling IDs:

```sh
python3 host_service.py --serial /dev/serial/by-id/YOUR_RS485_ADAPTER --ids 1-30 --web-port 8080
```

On Windows use its COM port, for example `--serial COM5`. The bus is **115200,
8N1**, with automatic adapter direction control. Connect A/B/reference ground;
feeders still use their own power supply. Use one bus master. Close independent
serial tools while the host owns the adapter.

### Start automatically on Debian, port 80

Copy the `V485-feeder` folder to `/opt/microsmt/V485-feeder`. Edit
`microsmt-host.service.example`: replace `YOUR_LOGIN` and `YOUR_RS485_ADAPTER`
with the machine's account and adapter path. That account needs serial access
through `dialout`; group changes take effect on its next login.

```sh
sudo cp microsmt-host.service.example /etc/systemd/system/microsmt-host.service
sudo systemctl daemon-reload
sudo systemctl enable --now microsmt-host.service
systemctl status microsmt-host.service
journalctl -u microsmt-host.service -n 40
```

The unit grants permission to bind port 80 without running Python as root.
Browse to `http://machine-hostname/`; hostname resolution must already work on
the network. The host does not configure DNS, router forwarding or encryption.
HTTP binds all IPv4 interfaces; feeder TCP stays on loopback. Change
`--web-host`, `--web-port` or `--tcp-port` if needed.

The service example stores stock in `/var/lib/microsmt/stock.sqlite3`.
Standalone runs default to `~/.v485/stock.sqlite3`. Polling IDs persist there.
After an adapter disconnect, inspect the connection and restart the service.

## Connect OpenPnP

Keep the Smoothieboard on OpenPnP's **direct serial motion driver**. Add a
separate regular **GcodeDriver** for feeders, without axes:

| Setting | Value |
| --- | --- |
| Communications | TCP, `127.0.0.1`, port `5001` |
| Actuator double command | `M600 N{IntegerValue} F0` |
| Actuator value | Feeder bus ID, 1–99 |
| Confirmation regex | `^ok(?:\s.*)?$` |
| Error regex | `(?i)^error:.*$` |
| Command timeout | At least 20,000 ms |

`F0` uses the feeder's saved advance. An explicit F value counts optical sensor
events, not millimetres. Use the synchronous GcodeDriver for this feeder path;
the motion driver can retain OpenPnP's asynchronous operation independently.

The host sends each advance once and returns `ok` after the matching feeder
reports DONE. Lost replies cause status checks, not another advance. Faults or
unknown movement outcomes return an error for inspection. `M115` identifies the
host; `M400` checks bus idle. Machine-motion commands are not accepted here.

### Optional OpenPnP companion

Copy `OpenPnP-Web.py` into OpenPnP's scripts folder. On this machine that is
`~/.openpnp2/scripts`. For automatic startup on Linux:

```sh
cd ~/.openpnp2/scripts
mkdir -p Events
ln -sfn ../OpenPnP-Web.py Events/Startup.MicroSMTWeb.py
```

Run **Scripts → Refresh Scripts → OpenPnP-Web** once if OpenPnP is already open.
Future launches run it automatically. After replacing the script, run it again
or let the next OpenPnP launch load it. It listens only on `127.0.0.1:5004`.
That connection edits configuration and reads job data; it is not a second
serial or motion bridge.

Without the companion, feeder status, stock, settings, tests and updates still
work. Catalogue edits and loaded-job checks require OpenPnP and the companion.

## The web pages

| Page | Use |
| --- | --- |
| `/` — Feeders | Online/offline overview, firmware, state, errors, spacing and stock |
| `/parts` | Create/edit native parts; select package and height |
| `/packages` | Footprint preview, description and compatible tips; create/copy packages |
| `/job` — Job stock | Remaining placements: Part, Need, Stock, Result; Refresh to recheck |
| `/firmware` | Built application, single/bulk update and queue status |
| `/settings` | Polling IDs, bus ID assignment and selected-unit details |

**All / Online / Offline** filters include remembered feeders and polling IDs
that have not answered. Offline rows retain their last known details. A row's
**Configure**, **Reel / stock** and **Test** buttons open compact popovers.

### Configure a feeder

Pause feeder commands, then set width, feed/peel direction, NC/NO switch
polarity and advance spacing. Bus ID is a fixed label here; assign IDs in Settings with
physical menu 01 selected on the feeder. Width is saved on the feeder. An 8 mm feeder has 2 mm sensor steps; wider feeders have 4 mm
steps. Spacing must be an exact multiple of that step, up to 99 events.

Saves target the known hardware UID, skip unchanged values and read settings
back. They reject active units and motor faults; invalid options can be repaired
while E3 is latched. A partial save reports the actual state
rather than automatically repeating a write.

### Reel stock and parts

Check Set quantity to enter a new remaining quantity; leave it unchecked for
label/part edits. Set part spacing and the low-stock threshold as needed. Movement
is counted from the optical sensor, including manual/partial advances. Stock
belongs to the physical feeder UID and survives bus ID changes. It is an
estimate: empty pockets, failed picks and unpowered tape movement are not
measured. Reverse sensor movement also consumes the estimate; correct it after
unloading/reversing tape. MCU resets mark the count uncertain. Low or unknown
stock never blocks a confirmed feeder advance.

Select an OpenPnP part and save. The companion assigns it to the matching bus
ID, preserving pickup coordinates. A missing powered feeder is created disabled;
OpenPnP must be disabled and the job stopped for creation. Teach pickup and
then enable it in OpenPnP. If sync fails, the reel is saved and **Retry sync**
retries only the part assignment, without resetting stock usage.

Parts and packages are edited only on Save, with OpenPnP idle and the job
stopped. **Compatible tips** in the part popup opens its package editor. Tip
compatibility applies to every part using that package. Head/tip compatibility
is read from OpenPnP; creation, holder allocation, changer teaching and physical
nozzle management stay there. Footprint previews are geometry, not photographs.

### Job stock

The check uses remaining enabled placements from the loaded OpenPnP job. It
shows sufficient stock, shortages, unknown/uncertain counts and feeder problems.
Stock in trays or strip feeders is untracked. This is a stock check, not a
machine-readiness test, and it never starts or controls a job.

## Firmware updates

The current feeder application is **0.1.3**. Build from `../CODE_feeder`:

```sh
pio run -e v485
```

The build automatically writes `USB_host/firmware.json` with the binary and
version/CRC32/SHA-256 metadata. Copy that generated bundle to the machine's
`USB_host` folder when deploying a new build. Replacing the bundle does not
require a service restart. Do not select a binary manually in the web page.

The overview shows **Current / Update available / Unknown**, comparing image
CRC32 and size. Firmware/settings are read on discovery, reconnect, MCU reboot
and host startup; normal heartbeat traffic uses DIAG only. Responding units are
checked regularly; a missing-ID probe gets a slot every 0.5 seconds and rotates
fairly across due IDs. More absent IDs increase discovery time. Polling continues
while feeder commands are paused; regular status remains polled.

At startup, firmware 0.1.3 sends one CRC-checked `ONLINE` packet with its UID,
replacing the text banner. A short ID-based delay staggers simultaneous starts.
The host uses it to bring that ID's next normal status check forward. There are
no acknowledgements or retries; collisions or a missed hello fall back to
polling. A hello alone never marks a feeder online.

Click a row's **Update**, or **Update all outdated** for connected assigned
feeders. Both use the same server-owned queue and progress popup. Commands pause
automatically. Each target's identity/image is checked, the application uploaded
and CRC verified. A failed unit is marked Failed while the queue continues with
the others; retry it explicitly. Current units skip flashing. Refreshing/closing
the browser does not interrupt a queue. Feeders stay paused afterward; resume
when ready. Queue results last until the host restarts.

Application updates preserve feeder settings and use the installed bootloader.
No bootloader update or firmware-backup step is part of this workflow.
See [firmware instructions](../CODE_feeder/README.md) for SWD and serial tools.

## Switch/input test

On firmware 0.1.3, open **Test → Pause & start input test**. Wait for **Input
test active · both motors inhibited**. Then operate the switch/buttons or turn
the index sensor to see raw contact, interpreted peel request, transition count,
optical total, motor state and uptime. The test inhibits both motors and local
feeding. It does not change settings or stock baselines.

Closing the popup leaves test mode active. **End test** or a power cycle ends
it; existing faults remain latched. All widths can resume idle peeling on
exit only if already armed by an ordinary feed. If a reply is lost, use Read inputs to confirm state. The popup reads about
four times per second through the host's existing bus owner.

All widths start with peel take-up off until the first normal feed or
feed-button press. Once armed, the switch also controls idle take-up, with the
ten-second peel timeout. **Clear error** clears motor timeouts or Stop without rebooting or
changing settings. Peel stays inhibited until the next ordinary feed; the host
remains paused. Settings faults need the underlying settings corrected.
See [firmware behaviour](../CODE_feeder/README.md).

## Saving and bench controls

Reel **Part spacing** and hardware **Feed pitch** save the same default advance
on the feeder, with readback. Pause feeder commands before changing spacing.
Changing the label or selected part keeps consumption intact. Check **Set
quantity** only when loading a reel or correcting the remaining quantity.

Configure includes **Width** for commissioning and **Advance 1** for bench
checks. Advance requires paused feeder commands and a matching hardware UID;
OpenPnP TCP advances remain blocked until resumed. It sends one request and
never retries uncertain motion. A recent **Restarted** note appears in Last
seen when the existing runtime token changes; the tooltip counts restarts
observed since the host started.

A failed firmware/settings read is retried after five seconds. Successful
metadata stays cached. New bus IDs are saved to the polling list.

Remembered units waiting in the bootloader show **Bootloader** and can be
updated again. An explicit per-ID update also probes for recovery when the
application is offline. The installed bootloader has no UID query, so recovery
uses the addressed READY response; ordinary application updates still verify
UID. No bootloader rewrite is required.

An invalid motor/switch record can be repaired in Configure. The firmware keeps
motors inhibited while width, options and count are saved; Clear Error then
releases the runtime settings fault. EEPROM write failures remain blocked.

## API and checks

The dashboard's API is served on the same HTTP port:

| Route | Purpose |
| --- | --- |
| `GET /api/status`, `GET /api/events` | Cached feeder status and SSE activity |
| `GET /api/catalogue`, `GET /api/job` | OpenPnP catalogue and remaining-job stock |
| `POST /api/maintenance`, `/api/polling` | Pause/resume and polling IDs |
| `POST /api/refresh`, `/api/configure`, `/api/assign`, `/api/test` | Read details, save hardware settings, assign ID and input test |
| `POST /api/advance` | One default advance while feeder commands are paused; address and UID required |
| `POST /api/clear-error` | Clear runtime faults on the selected address/UID; requires firmware 0.1.3 |
| `POST /api/stock`, `/api/part-sync` | Reel save and explicit part-sync retry |
| `POST /api/openpnp` | Create/edit parts/packages and add powered feeders |
| `POST /api/update-bundled`, `/api/update-all-bundled` | Queue the displayed bundle, pinned by SHA-256 |
| `POST /api/image`, `/api/update?address=ID` | Inspect raw application bytes, or queue an explicit raw-image update |

JSON requests use `Content-Type: application/json`; image routes use
`application/octet-stream`. Browser POSTs use the page's own origin. There is
no arbitrary serial-packet endpoint. Stock is in SQLite by hardware UID.

From `USB_host`, hardware-free checks include:

```sh
python3 check_host.py
python3 check_polling.py
python3 check_startup.py
python3 check_clear_error.py
python3 check_review_fixes.py
python3 check_details.py
python3 check_bulk.py
python3 check_bundle.py
python3 check_activity.py
python3 check_input_test.py
python3 check_part_sync.py
python3 check_openpnp_proxy.py
python3 check_dashboard_tools.py
node check_firmware_ui.js
```

The host check also needs native `gcc`. `check_openpnp_web.py` runs with
OpenPnP's bundled Jython/libraries in an isolated JVM. Checks use simulated
feeders/temporary profiles; they do not operate the machine. Real tape travel,
switch mounting, pickup and nozzle changer operation must be tested at the bench.
