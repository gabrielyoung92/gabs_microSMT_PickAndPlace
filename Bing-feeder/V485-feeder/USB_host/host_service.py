#!/usr/bin/env python3
"""MicroSMT machine web console and local OpenPnP feeder/motion TCP service.

One owner of a direct auto-direction USB-RS485 adapter, at 115200 8N1.
Stock is informational. Hardware control/deadlines remain on each STM32.
Original MicroSMT authors retain credit; local changes by Gab with ChatGPT.
"""
import argparse
import json
import logging
import os
from pathlib import Path
import re
import secrets
import socket
import socketserver
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

# Reuse the maintained packet, update and ID tools rather than fork their wire
# protocol. Run this folder with its sibling CODE_feeder folder present.
TOOLS = Path(__file__).resolve().parents[1] / "CODE_feeder" / "tools"
sys.path.insert(0, str(TOOLS))
from rs485_upload import APP_MAX, Link, UpdateError, decode_packet, fields, inspect_image, packet, upload
from assign_id import assign
from motion import Motion, MotionError, MotionServer

VERSION = "0.1.0"
BAUD = 115200
FAULTS = {0: "none", 1: "index_timeout", 2: "peel_timeout", 3: "settings_error"}
FEED_STATES = ("idle", "reserved", "running", "fault")
MODES = ("normal", "menu", "assign_id", "edit_id", "edit_count", "edit_type")
log = logging.getLogger("v485")


class ServiceError(Exception):
    pass


def integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be {minimum}..{maximum}")
    return value


def parse_ids(text):
    if not isinstance(text, str):
        raise ValueError("Polling addresses must be text")
    result = set()
    for item in text.split(","):
        limits = item.strip().split("-")
        if len(limits) not in (1, 2) or not all(n.isdecimal() for n in limits):
            raise ValueError("IDs must look like 0,1-24 or 1,7,12")
        low, high = int(limits[0]), int(limits[-1])
        if not 0 <= low <= high <= 99:
            raise ValueError("Polling addresses must be 0..99; advances require 1..99")
        result.update(range(low, high + 1))
    return sorted(result)


def state_fields(flags):
    state, mode = (flags >> 16) & 15, (flags >> 20) & 15
    fault = (flags >> 8) & 255
    return dict(default_count=flags & 255, fault_code=fault,
                fault=FAULTS.get(fault, f"unknown_{fault}"),
                state=FEED_STATES[state] if state < len(FEED_STATES) else "unknown",
                mode=MODES[mode] if mode < len(MODES) else "unknown",
                switch_closed=bool(flags & (1 << 24)), peel_running=bool(flags & (1 << 25)),
                ready=bool(flags & (1 << 26)), assigned=bool(flags & (1 << 27)),
                configured=bool(flags & (1 << 29)),
                nominal_step_um=(4000 if flags & (1 << 28) else 2000) if flags & (1 << 29) else 0,
                variant=f"{(8, 12, 16, 24)[(flags >> 30) & 3]}mm" if flags & (1 << 29) else "unconfigured")


class Stock:
    """PC inventory keyed by MCU UID, independent of a feeder's editable ID."""
    def __init__(self, path):
        self.lock = threading.RLock()
        self.persistent = str(path) != ":memory:"
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS feeders (
            uid TEXT PRIMARY KEY, address INTEGER UNIQUE, token TEXT, counter INTEGER,
            flags INTEGER, seen REAL, error TEXT NOT NULL DEFAULT '',
            label TEXT NOT NULL DEFAULT '', loaded INTEGER, pitch INTEGER NOT NULL DEFAULT 1,
            used_pulses INTEGER NOT NULL DEFAULT 0, low INTEGER NOT NULL DEFAULT 50,
            uncertain INTEGER NOT NULL DEFAULT 1)""")
        self.db.commit()

    def observe(self, address, uid, token, counter, flags):
        if token == "0000000000000000":
            raise ValueError("Unclaimed telemetry token")
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM feeders WHERE uid=?", (uid,)).fetchone()
            # A replacement module at an old ID must not inherit the old reel.
            self.db.execute("UPDATE feeders SET address=NULL WHERE address=? AND uid<>?", (address, uid))
            if row is None:
                self.db.execute("INSERT INTO feeders(uid,address,token,counter,flags,seen,pitch) VALUES(?,?,?,?,?,?,?)",
                                (uid, address, token, counter, flags, time.time(), max(1, flags & 255)))
            else:
                uncertain = row["uncertain"]
                if row["token"] != token:
                    # New MCU boot: its current counter is known, but movement
                    # between our last poll and that reset may have been lost.
                    delta, uncertain = counter, 1
                else:
                    delta = (counter - row["counter"]) & 0xFFFFFFFF
                    if delta >= 0x80000000:
                        delta, uncertain = 0, 1
                self.db.execute("""UPDATE feeders SET address=?,token=?,counter=?,flags=?,seen=?,error='',
                    used_pulses=used_pulses+?,uncertain=? WHERE uid=?""",
                                (address, token, counter, flags, time.time(), delta, uncertain, uid))

    def failed(self, address, error):
        with self.lock, self.db:
            self.db.execute("UPDATE feeders SET error=? WHERE address=?", (str(error)[:240], address))

    def load(self, uid, label, quantity, pitch, low):
        integer(quantity, 0, 1_000_000_000, "Loaded quantity")
        integer(pitch, 1, 99, "Pulses per part")
        integer(low, 0, 1_000_000_000, "Low-stock threshold")
        if not isinstance(label, str) or len(label) > 128:
            raise ValueError("Reel label must be at most 128 characters")
        with self.lock, self.db:
            self.db.execute("UPDATE feeders SET label=?,loaded=?,pitch=?,used_pulses=0,low=?,uncertain=0 WHERE uid=?",
                            (label, quantity, pitch, low, uid))

    def rows(self):
        with self.lock:
            rows = [dict(row) for row in self.db.execute("SELECT * FROM feeders ORDER BY address IS NULL,address,uid")]
        for row in rows:
            row.update(state_fields(row.pop("flags")))
            row["used"] = row["used_pulses"] / row["pitch"]
            row["remaining"] = None if row["loaded"] is None else max(0, row["loaded"] - row["used"])
            row["low_stock"] = row["remaining"] is not None and row["remaining"] <= row["low"]
            row["age_seconds"] = max(0, time.time() - row["seen"])
        return rows

    def close(self):
        self.db.close()


class Feeders:
    def __init__(self, port, stock, ids, reply_timeout=0.3, feed_timeout=12.0, poll_interval=0.1):
        self.port, self.stock, self.ids = port, stock, list(ids)
        # One lock covers whole operations, including FEED/STATUS and updates.
        self.bus = threading.RLock()
        self.control = threading.RLock()
        self.maintenance = self.updating = False
        self.reply_timeout, self.feed_timeout, self.poll_interval = reply_timeout, feed_timeout, poll_interval
        self.session, self.sequence = secrets.randbits(32), 0
        self.errors = {}
        self.firmware = {}
        self.update_status = None
        self.background_interval = 1.0

    def read_firmware(self, address):
        """Explicit read only; INFO is unnecessary traffic during normal polls."""
        integer(address, 0, 99, "Address")
        with self.bus:
            uid = self.observe(address)
            try:
                variant, size, checksum = fields(Link(self.port, address).request(
                    "INFO", {"APP"}, timeout=self.reply_timeout, attempts=1), "APP", 3)
                info = dict(variant=variant, size=size, crc32=f"{checksum:08X}", read_at=time.time())
            except (OSError, TimeoutError, UpdateError) as error:
                info = dict(error=str(error)[:240])
            with self.control:
                self.firmware[uid] = info

    def set_maintenance(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("enabled must be true or false")
        with self.control:
            if self.updating and not enabled:
                raise ServiceError("Wait for the firmware upload to finish")
            self.maintenance = enabled

    def _identity(self, address, nonce):
        link = Link(self.port, address)
        reply = link.request(f"IDENT {nonce:08X}", {"IDENT"}, timeout=self.reply_timeout, attempts=1)
        values = fields(reply, "IDENT", 5)
        if values[0] != nonce:
            raise UpdateError("Stale identity reply")
        return "".join(f"{n:08X}" for n in values[1:4])

    def observe(self, address):
        """Caller holds bus; inventory failures never change motor state."""
        nonce = secrets.randbits(32)
        uid = self._identity(address, nonce)
        link = Link(self.port, address)
        reply = link.request(f"DIAG {nonce:08X}", {"DIAG"}, timeout=self.reply_timeout, attempts=1)
        values = fields(reply, "DIAG", 5)
        if values[0] != nonce:
            raise UpdateError("Stale diagnostic reply")
        if not (values[1] | values[2]):
            token = secrets.randbits(64) or 1
            reply = link.request(f"MONITOR {nonce:08X} {token >> 32:08X} {token & 0xFFFFFFFF:08X}",
                                 {"DIAG"}, timeout=self.reply_timeout, attempts=1)
            values = fields(reply, "DIAG", 5)
            if values[0] != nonce or not (values[1] | values[2]):
                raise UpdateError("Telemetry token was not claimed")
        token = f"{values[1]:08X}{values[2]:08X}"
        self.stock.observe(address, uid, token, values[3], values[4])
        with self.control:
            self.errors.pop(address, None)
        return uid

    def observe_safely(self, address):
        try:
            return self.observe(address)
        except Exception as error:
            # Telemetry/inventory is optional: even a damaged database must not
            # turn a sensor-confirmed DONE into an OpenPnP error.
            message = str(error)[:240]
            with self.control:
                changed = self.errors.get(address) != message
                self.errors[address] = message
            if changed:
                log.warning("ID %s telemetry: %s", address, message)
            try:
                self.stock.failed(address, error)
            except Exception:
                log.exception("Could not record inventory error; feeding is independent")
            return None

    def _motion_reply(self, address, tokens, deadline):
        while time.monotonic() < deadline:
            body = decode_packet(self.port.read_until(b"\n", 129), address)
            if body is None:
                continue
            label = body.split(" ", 1)[0]
            if label not in {"ACCEPT", "BUSY", "RUNNING", "DONE", "FAULT", "UNKNOWN"}:
                continue
            try:
                if fields(body, label, 2) == tokens:
                    return label
            except UpdateError:
                continue
        return None

    def feed(self, address, count):
        integer(address, 1, 99, "Feeder ID")
        integer(count, 0, 99, "Feed count")
        with self.control:
            if self.maintenance:
                raise ServiceError("Maintenance mode: advance rejected")
        if not self.bus.acquire(timeout=1):
            raise ServiceError("Bus busy: advance rejected before transmission")
        try:
            with self.control:
                if self.maintenance:
                    raise ServiceError("Maintenance mode: advance rejected")
            # Stock is deliberately absent from this acceptance decision.
            self.sequence = (self.sequence + 1) & 0xFFFFFFFF
            if not self.sequence:
                self.session, self.sequence = secrets.randbits(32), 1
            tokens = (self.session, self.sequence)
            text = f"{tokens[0]:08X} {tokens[1]:08X}"
            deadline = time.monotonic() + self.feed_timeout
            try:
                # Never retry FEED, including write/ack failures: it may have moved.
                self.port.write(packet(address, f"FEED {text} {count:08X}"))
                self.port.flush()
                result = self._motion_reply(address, tokens, min(deadline, time.monotonic() + self.reply_timeout))
                while True:
                    if result == "DONE":
                        return f"ok N{address} F{count}"
                    if result in {"BUSY", "FAULT", "UNKNOWN"}:
                        raise ServiceError(f"ID {address}: {result.lower()}; advance not confirmed")
                    if time.monotonic() >= deadline:
                        raise ServiceError(f"ID {address}: completion timeout; do not resend automatically")
                    self.port.write(packet(address, f"STATUS {text}"))
                    self.port.flush()
                    result = self._motion_reply(address, tokens, min(deadline, time.monotonic() + self.reply_timeout))
                    if result not in {"DONE", "BUSY", "FAULT", "UNKNOWN"}:
                        time.sleep(self.poll_interval)
            finally:
                # Even if telemetry/SQLite fails after DONE, the confirmed feed
                # still returns ok. Partial movement after faults is also counted.
                self.observe_safely(address)
        finally:
            self.bus.release()

    def load_stock(self, address, label, quantity, pitch, low=50):
        integer(address, 0, 99, "Address")
        # Validate before any serial operation or baseline changes.
        integer(quantity, 0, 1_000_000_000, "Loaded quantity")
        integer(pitch, 1, 99, "Pulses per part")
        integer(low, 0, 1_000_000_000, "Low-stock threshold")
        if not isinstance(label, str) or len(label) > 128:
            raise ValueError("Invalid reel label")
        with self.bus:
            self.stock.load(self.observe(address), label, quantity, pitch, low)

    def assign_id(self, address, new_id):
        integer(address, 0, 99, "Current address")
        integer(new_id, 1, 99, "New ID")
        with self.bus:
            with self.control:
                if not self.maintenance:
                    raise ServiceError("Enable maintenance before assigning an ID")
            assign(self.port, address, new_id)
            with self.control:
                self.ids = sorted((set(self.ids) - {address}) | {new_id})
                self.errors.pop(address, None)
            self.observe_safely(new_id)

    def update(self, address, image):
        integer(address, 0, 99, "Address")
        _, _, checksum = inspect_image(image)  # Validate before any BOOT/erase request.
        if not self.bus.acquire(blocking=False):
            raise ServiceError("Bus busy: firmware update was not started")
        try:
            with self.control:
                if not self.maintenance:
                    raise ServiceError("Enable maintenance before updating firmware")
                self.updating = True
                self.update_status = dict(address=address, stage="connecting", sent=0,
                                          size=len(image), crc32=f"{checksum:08X}",
                                          started=time.time(), error=None)
            def progress(stage, sent, total):
                with self.control:
                    self.update_status.update(stage=stage, sent=sent, size=total)
            succeeded = False
            try:
                upload(Link(self.port, address), image, progress=progress)
                succeeded = True
            except Exception as error:
                with self.control:
                    self.update_status.update(stage="failed", error=str(error)[:240])
                raise
            finally:
                if succeeded:
                    # DONE precedes the application's startup flashes. Allow
                    # it to initialise before attempting optional telemetry.
                    deadline = time.monotonic() + 3
                    while not self.observe_safely(address) and time.monotonic() < deadline:
                        time.sleep(0.1)
                    try:
                        self.read_firmware(address)
                    except Exception:
                        pass  # Upload verification already succeeded; telemetry is optional.
                else:
                    self.observe_safely(address)
                with self.control:
                    self.updating = False
                    self.update_status["finished"] = time.time()
        finally:
            self.bus.release()

    def snapshot(self):
        with self.control:
            status = dict(version=VERSION, maintenance=self.maintenance, updating=self.updating,
                          polling_ids=list(self.ids), errors=dict(self.errors),
                          update=dict(self.update_status) if self.update_status else None,
                          firmware=dict(self.firmware),
                          stale_after_seconds=max(5, len(self.ids) *
                                                  (self.background_interval + self.reply_timeout) * 2))
        status["inventory_persistent"] = self.stock.persistent
        try:
            status["feeders"] = self.stock.rows()
        except Exception as error:
            status["feeders"], status["inventory_error"] = [], str(error)[:240]
        return status

    def poll(self, stopped, interval=1.0):
        self.background_interval = interval
        cursor = 0
        while not stopped.wait(interval):
            with self.control:
                ids = list(self.ids)
                paused = self.maintenance
            if not ids or paused or not self.bus.acquire(blocking=False):
                continue
            try:
                self.observe_safely(ids[cursor % len(ids)])
                cursor += 1
            finally:
                self.bus.release()


class GcodeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, port, feeders):
        self.feeders, self.client = feeders, threading.Lock()
        super().__init__(("127.0.0.1", port), GcodeHandler)


class GcodeHandler(socketserver.StreamRequestHandler):
    def handle(self):
        if not self.server.client.acquire(blocking=False):
            self.wfile.write(b"error: another OpenPnP client is already connected\n")
            return
        try:
            while True:
                raw = self.rfile.readline(129)
                if not raw:
                    return
                if len(raw) > 128 or not raw.endswith(b"\n") or b"\0" in raw:
                    self.wfile.write(b"error: invalid/overlong command; connection closed\n")
                    return
                try:
                    text = raw.decode("ascii").strip()
                    if text.upper() == "M115":
                        reply = f"FIRMWARE_NAME:V485_USB_HOST FIRMWARE_VERSION:{VERSION}\nok"
                    elif text.upper() == "M400":
                        if self.server.feeders.maintenance:
                            raise ServiceError("Maintenance mode")
                        if not self.server.feeders.bus.acquire(timeout=1):
                            raise ServiceError("Bus busy")
                        try:
                            reply = "ok"
                        finally:
                            self.server.feeders.bus.release()
                    else:
                        match = re.fullmatch(r"(?:M600[ \t]+)?N([0-9]{1,2})[ \t]+F([0-9]{1,2})", text, re.I)
                        if not match:
                            raise ValueError("expected M600 N1..99 F0..99")
                        reply = self.server.feeders.feed(int(match[1]), int(match[2]))
                except (UnicodeError, ValueError, ServiceError, UpdateError, OSError, TimeoutError) as error:
                    reply = "error: " + str(error).replace("\n", " ").replace("\r", " ")
                self.wfile.write((reply + "\n").encode("ascii", errors="replace"))
                self.wfile.flush()
        except OSError:
            # An in-flight feed is never replayed after a broken TCP connection.
            log.info("OpenPnP connection closed")
        finally:
            self.server.client.release()


class WebServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, feeders, demo=False, tcp_port=5001, host="127.0.0.1", motion=None, motion_port=5003):
        self.feeders, self.demo, self.tcp_port = feeders, demo, tcp_port
        self.motion, self.motion_port = motion, motion_port
        super().__init__((host, port), WebHandler)


class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def respond(self, status, value, content_type="application/json"):
        data = json.dumps(value).encode() if content_type == "application/json" else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self.respond(200, Path(__file__).with_name("dashboard.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/status":
            status = self.server.feeders.snapshot()
            status["demo"] = self.server.demo
            status["tcp_port"] = self.server.tcp_port
            status["motion"] = self.server.motion.snapshot() if self.server.motion else {"configured": False}
            status["motion"]["tcp_port"] = self.server.motion_port
            self.respond(200, status)
        else:
            self.respond(404, {"error": "Unknown path"})

    def do_POST(self):
        try:
            # Match the page's actual hostname/IP, including the implicit HTTP
            # port 80. LAN clients need no login; unrelated sites cannot POST.
            origin = self.headers.get("Origin")
            if origin:
                source = urlsplit(origin)
                target = urlsplit("http://" + self.headers.get("Host", ""))
                if (source.scheme != "http" or not source.hostname or source.username or source.password
                        or source.path or source.query or source.fragment
                        or (source.hostname, source.port or 80) != (target.hostname, target.port or 80)):
                    self.respond(403, {"error": "Use the feeder page on this host"})
                    return
            path = urlsplit(self.path)
            size = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= size <= APP_MAX:
                self.close_connection = True
                self.respond(413, {"error": "Missing or oversized request body"})
                return
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError("Incomplete request")
            feeders = self.server.feeders
            if path.path in {"/api/update", "/api/image"}:
                if self.headers.get_content_type() != "application/octet-stream":
                    raise ValueError("Send a firmware.bin as application/octet-stream")
                if path.path == "/api/image":
                    variant, size, checksum = inspect_image(raw)
                    self.respond(200, dict(variant=variant, size=size, crc32=f"{checksum:08X}"))
                    return
                if self.server.demo:
                    raise ServiceError("Demo mode cannot flash firmware")
                params = parse_qs(path.query)
                if set(params) != {"address"} or len(params["address"]) != 1:
                    raise ValueError("One address is required")
                feeders.update(int(params["address"][0]), raw)
            else:
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("Use application/json")
                args = json.loads(raw)
                if not isinstance(args, dict):
                    raise ValueError("Expected a JSON object")
                if path.path == "/api/motion":
                    if self.server.motion is None:
                        raise ServiceError("Motion controller is not configured")
                    self.server.motion.action(args)
                elif path.path == "/api/maintenance":
                    feeders.set_maintenance(args["enabled"])
                elif path.path == "/api/polling":
                    ids = parse_ids(args["ids"])
                    with feeders.control:
                        feeders.ids = ids
                elif path.path == "/api/refresh":
                    address = integer(args["address"], 0, 99, "Address")
                    feeders.read_firmware(address)
                elif path.path == "/api/stock":
                    feeders.load_stock(args["address"], args.get("label", ""), args["quantity"],
                                       args["pulses_per_part"], args.get("low", 50))
                elif path.path == "/api/assign":
                    feeders.assign_id(args["address"], args["new_id"])
                else:
                    self.respond(404, {"error": "Unknown path"})
                    return
            self.respond(200, {"ok": True})
        except (ValueError, KeyError, TypeError) as error:
            self.respond(400, {"error": str(error)})
        except (ServiceError, MotionError) as error:
            self.respond(409, {"error": str(error)})
        except (OSError, TimeoutError, UpdateError) as error:
            self.respond(503, {"error": str(error)})
        except sqlite3.Error:
            log.exception("Inventory database operation failed")
            self.respond(500, {"error": "Inventory database error; inspect the service log"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--serial", help="Direct USB-RS485 port, e.g. COM5 or /dev/serial/by-id/...")
    source.add_argument("--demo", action="store_true", help="Simulated machine and feeders; opens no hardware port")
    parser.add_argument("--motion-serial", help="Optional Smoothieware USB serial device; leave unset for feeders only")
    parser.add_argument("--motion-port", type=int, default=5003, help="Local OpenPnP motion TCP port (default: 5003)")
    parser.add_argument("--ids", default="1-24", help="Polling addresses, e.g. 0,1-24 (one unassigned module only)")
    parser.add_argument("--database", type=Path, help="Stock database (default: ~/.v485/stock.sqlite3; separate demo-stock.sqlite3 in demo)")
    parser.add_argument("--tcp-port", type=int, default=5001)
    parser.add_argument("--web-host", default="0.0.0.0", help="HTTP bind address (default: all IPv4 interfaces)")
    parser.add_argument("--web-port", type=int, default=80, help="HTTP port (default: 80)")
    parser.add_argument("--poll-interval", type=float, default=0.25, help="Seconds between polling one module")
    args = parser.parse_args()
    try:
        ids = parse_ids(args.ids)
        if not 0.05 <= args.poll_interval <= 60:
            raise ValueError("Poll interval must be 0.05..60 seconds")
        for port in (args.tcp_port, args.web_port, args.motion_port):
            integer(port, 1, 65535, "Listen port")
        if len({args.tcp_port, args.web_port, args.motion_port}) != 3:
            raise ValueError("Feeder TCP, motion TCP and web ports must differ")
        if args.demo and args.motion_serial:
            raise ValueError("Demo cannot open a hardware motion port")
        if args.motion_serial and args.motion_serial == args.serial:
            raise ValueError("Motion and feeder serial devices must differ")
    except ValueError as error:
        parser.error(str(error))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.database is None:
        args.database = Path.home() / ".v485" / ("demo-stock.sqlite3" if args.demo else "stock.sqlite3")
    try:
        args.database.parent.mkdir(parents=True, exist_ok=True)
        stock = Stock(args.database)
    except (OSError, sqlite3.Error):
        log.exception("Inventory storage unavailable; using temporary stock data, feeding remains enabled")
        stock = Stock(":memory:")
    stopped = threading.Event()
    servers = []
    port = None
    motion = None
    motion_port = None
    try:
        if args.demo:
            from simulated_bus import SimulatedBus
            port = SimulatedBus()
        else:
            import serial
            # Windows serial opens are exclusive; POSIX needs this explicit flag.
            options = {"exclusive": True} if os.name == "posix" else {}
            port = serial.Serial(args.serial, BAUD, timeout=0.05, write_timeout=2, **options)
            port.reset_input_buffer()
        feeders = Feeders(port, stock, ids)
        if args.demo:
            from simulated_motion import SimulatedMotion
            motion_port = SimulatedMotion()
        elif args.motion_serial:
            # Set modem lines before opening; avoid an unnecessary DTR/RTS
            # transition on the motion controller. Never reset/reopen it here.
            motion_port = serial.Serial(port=None, baudrate=BAUD, timeout=0.05, write_timeout=2, **options)
            motion_port.dtr = motion_port.rts = False
            motion_port.port = args.motion_serial
            motion_port.open()
        if motion_port is not None:
            motion = Motion(motion_port)
            servers.append(MotionServer(args.motion_port, motion))
        servers.append(GcodeServer(args.tcp_port, feeders))
        servers.append(WebServer(args.web_port, feeders, args.demo, args.tcp_port, args.web_host,
                                 motion=motion, motion_port=args.motion_port))
        for server in servers:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
        poller = threading.Thread(target=feeders.poll, args=(stopped, args.poll_interval), daemon=True)
        poller.start()
        web_name = socket.gethostname() if args.web_host == "0.0.0.0" else args.web_host
        web_suffix = "" if args.web_port == 80 else f":{args.web_port}"
        log.info("%sOpenPnP TCP 127.0.0.1:%s; machine page http://%s%s (bind %s:%s)",
                 "DEMO: " if args.demo else "", args.tcp_port, web_name, web_suffix,
                 args.web_host, args.web_port)
        if motion:
            log.info("%sMotion TCP 127.0.0.1:%s; web manual controls enabled",
                     "DEMO: " if args.demo else "", args.motion_port)
        try:
            while not stopped.wait(1):
                pass
        except KeyboardInterrupt:
            log.info("Stopping; no motion requests will be replayed")
        finally:
            stopped.set()
            feeders.set_maintenance(True)
            for server in servers:
                server.shutdown()
            # Closing a hardware handle wakes serial reads. All motion remains
            # bounded by the MCU's own sensor count/deadline if the PC exits.
            port.close()
            poller.join(timeout=2)
    except (OSError, ImportError) as error:
        parser.exit(1, f"Could not start host: {error}\n")
    finally:
        for server in servers:
            server.server_close()
        if port is not None:
            port.close()
        if motion is not None:
            motion.close()
        elif motion_port is not None:
            motion_port.close()
        # Request threads are daemons; avoid closing their SQLite connection
        # underneath a final in-flight telemetry write during process shutdown.


if __name__ == "__main__":
    main()
