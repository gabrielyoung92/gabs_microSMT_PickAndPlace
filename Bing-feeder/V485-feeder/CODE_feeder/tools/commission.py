#!/usr/bin/env python3
"""Flash/configure one isolated V485 board, recording verified ID/type/UID.

MicroSMT-derived firmware; upstream credit is in ../README.md.
No feed commands. Keep only the commissioning board on the RS485 bus.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import time

from assign_id import assign, identify
from configure_unit import configure as configure_options, set_count
from rs485_upload import Link, UpdateError, fields, inspect_image, upload

PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[2]


def planned_width(address):
    if not 1 <= address <= 30:
        raise ValueError("This batch uses IDs 1..30")
    return 8 if address <= 20 else 12 if address <= 27 else 16


def configure(port, address, new_id, width, expected_uid=None, wait=90):
    if width not in (8, 12, 16, 24) or not 1 <= new_id <= 99:
        raise ValueError("Width must be 8/12/16/24 and ID must be 1..99")
    deadline = time.monotonic() + wait
    print("Hold PA2 for 2–4 seconds, release at menu 01; waiting for selection...", flush=True)
    while True:
        uid, armed = identify(Link(port, address), secrets.randbits(32), 1)
        if expected_uid is not None and uid != expected_uid:
            raise UpdateError("RS485 UID does not match the selected SWD board")
        if armed:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("No local menu 01 selection; configuration not written")
        time.sleep(0.2)
    nonce = secrets.randbits(32)
    body = "SETTYPE " + " ".join(f"{n:08X}" for n in (nonce, *uid, width))
    try:
        Link(port, address).request(body, {"TYPESET"}, attempts=1,
                                   expected=f"TYPESET {nonce:08X} {width:08X}")
    except TimeoutError:
        pass  # Verify an uncertain save; never repeat the write automatically.
    result = fields(Link(port, address).request(f"TYPE {nonce:08X}", {"TYPE"}), "TYPE", 4)
    if result[:2] != (nonce, width):
        raise UpdateError("Saved width did not verify")
    configured_uid, _ = configure_options(port, address, (int(width == 8), 0, 0))
    if configured_uid != uid:
        raise UpdateError("UID changed while saving the default profile")
    set_count(port, address, 2 if width == 8 else 1)
    saved_uid = assign(port, address, new_id)
    if saved_uid != uid:
        raise UpdateError("UID changed while assigning ID")
    result = fields(Link(port, new_id).request(f"TYPE {nonce:08X}", {"TYPE"}), "TYPE", 4)
    diag = fields(Link(port, new_id).request(f"DIAG {nonce:08X}", {"DIAG"}), "DIAG", 5)
    flags = diag[-1]
    if result[:2] != (nonce, width) or result[3] != (2000 if width == 8 else 4000) or diag[0] != nonce or flags & 0x00FFFF00 or flags & ((1 << 26) | (1 << 27) | (1 << 29)) != ((1 << 26) | (1 << 27) | (1 << 29)):
        raise UpdateError("Final type/idle/fault verification failed")
    return dict(id=new_id, width_mm=width, uid="".join(f"{n:08X}" for n in uid),
                default_count=result[2], nominal_step_um=result[3], flags=f"{flags:08X}")


def self_check():
    from rs485_upload import packet, decode_packet
    class Port:
        def __init__(self, lost=False):
            self.address, self.width, self.armed = 0, 0, 1
            self.reply, self.commands, self.lost = [], [], lost
            self.options, self.count = (0, 0, 0), 1
        def reset_input_buffer(self): self.reply.clear()
        def flush(self): pass
        def read_until(self, *args): return self.reply.pop(0) if self.reply else b""
        def write(self, raw):
            address = int(raw[1:3]); body = decode_packet(raw, address)
            self.commands.append(body)
            assert body.split()[0] not in ('FEED','BOOT','BEGIN','DATA')
            if address != self.address: return
            parts = body.split(); nonce = parts[1]
            def reply(text): self.reply.append(packet(address, text))
            if parts[0] == 'IDENT': reply(f'IDENT {nonce} 00000011 00000022 00000033 {self.armed:08X}')
            elif parts[0] == 'SETTYPE':
                self.width = int(parts[-1],16)
                if not self.lost: reply(f'TYPESET {nonce} {self.width:08X}')
            elif parts[0] == 'TYPE': reply(f'TYPE {nonce} {self.width:08X} {self.count:08X} {(2000 if self.width == 8 else 4000):08X}')
            elif parts[0] == 'CONFIG': reply('CONFIG ' + nonce + ''.join(f' {v:08X}' for v in self.options))
            elif parts[0] == 'SETCONFIG':
                self.options = tuple(int(v,16) for v in parts[-3:])
                reply('CONFIGSET ' + nonce + ''.join(f' {v:08X}' for v in self.options))
            elif parts[0] == 'SETCOUNT':
                self.count = int(parts[-1],16)
                reply(f'COUNTSET {nonce} {self.count:08X}')
            elif parts[0] == 'SETID':
                self.address, self.armed = int(parts[-1],16), 0
                reply(f'ID {nonce} {self.address:08X}')
            elif parts[0] == 'DIAG': reply(f'DIAG {nonce} 00000000 00000000 00000000 2C000001')
    # Keep occupancy probes fast in the offline fake; production uses its default.
    global assign
    actual_assign = assign
    def fast_assign(port, address, new_id):
        return actual_assign(port, address, new_id, timeout=0.001)
    assign = fast_assign
    try:
        for width, lost in ((8,False),(12,False),(16,False),(24,False),(8,True)):
            port = Port(lost)
            result = configure(port, 0, 1, width, (0x11,0x22,0x33), wait=0.01)
            assert result['id']==1 and result['width_mm']==width and result['default_count']==(2 if width == 8 else 1)
            assert port.options == (int(width == 8), 0, 0)
            assert sum(c.startswith('SETTYPE ') for c in port.commands)==1
            assert sum(c.startswith('SETID ') for c in port.commands)==1
    finally: assign = actual_assign
    assert [planned_width(n) for n in range(1,31)] == [8]*20+[12]*7+[16]*3
    print('Commissioning: batch plan, type save, lost type ACK, UID and ID verification passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port")
    parser.add_argument("--address", type=int, default=0, help="Current bus ID; normally 0 for a new board")
    parser.add_argument("--new-id", type=int)
    parser.add_argument("--width", type=int, choices=(8, 12, 16, 24), help="Default: owner's 30-board plan")
    parser.add_argument("--install-loader", action="store_true", help="Back up flash and install universal loader over SWD first")
    parser.add_argument("--stlink", help="ST-Link serial, required with --install-loader")
    parser.add_argument("--configure-only", action="store_true", help="Skip application upload")
    parser.add_argument("--log", type=Path, default=REPO / ".local/v485-batch")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    if not args.port or args.new_id is None or not 0 <= args.address <= 99 or not 1 <= args.new_id <= 99:
        parser.error("Supply --port, --address 0..99 and --new-id 1..99")
    width = args.width if args.width is not None else planned_width(args.new_id)
    if args.install_loader and (not args.stlink or not re.fullmatch(r"[0-9A-Fa-f]+", args.stlink)):
        parser.error("--install-loader requires a hexadecimal --stlink serial")
    args.log.mkdir(parents=True, exist_ok=True)
    ledger = args.log / "units.json"
    units = json.loads(ledger.read_text()) if ledger.exists() else {}
    app = (PROJECT / ".pio/build/v485/firmware.bin").read_bytes()
    manifest = inspect_image(app)
    expected_uid = None
    if args.install_loader:
        loader = PROJECT / ".pio/build/bootloader/firmware.bin"
        if not loader.is_file() or not 8 < loader.stat().st_size <= 8192:
            raise ValueError("Build the universal loader first")
        backup = args.log / f"before-id-{args.new_id:02d}-{time.time_ns()}.bin"
        cmds = ["init", "mdw 0x1ffff7e8 3", "reset halt",
                f"dump_image {{{backup}}} 0x08000000 0x10000",
                f"flash write_image erase {{{loader}}} 0x08000000 bin",
                f"verify_image {{{loader}}} 0x08000000 bin", "reset run", "shutdown"]
        invocation = ["openocd", "-f", "interface/stlink.cfg", "-c", f"adapter serial {args.stlink}",
                      "-f", "target/stm32f1x.cfg", "-c", "adapter speed 1000"]
        for cmd in cmds:
            invocation += ["-c", cmd]
        completed = subprocess.run(invocation, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        backup.with_suffix(".log").write_text(completed.stdout)
        print(completed.stdout, flush=True)
        completed.check_returncode()
        match = re.search(r"0x1ffff7e8:\s+([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})", completed.stdout)
        if not match:
            raise UpdateError("Could not confirm SWD UID")
        expected_uid = tuple(int(n, 16) for n in match.groups())
        previous = units.get(str(args.new_id))
        if previous and previous['uid'] != ''.join(f'{n:08X}' for n in expected_uid):
            raise UpdateError("This ID is already recorded against a different board; inspect ledger")
    import serial
    with serial.Serial(args.port, 115200, timeout=0.1, write_timeout=2, exclusive=True) as port:
        port.reset_input_buffer()
        if not args.configure_only:
            upload(Link(port, args.address), app)
            time.sleep(2)
        uid, _ = identify(Link(port, args.address), secrets.randbits(32), 1)
        if expected_uid is not None and uid != expected_uid:
            raise UpdateError("RS485 UID does not match SWD")
        uid_text = ''.join(f'{n:08X}' for n in uid)
        if str(args.new_id) in units and units[str(args.new_id)]['uid'] != uid_text:
            raise UpdateError("Requested ID belongs to another recorded board")
        if any(n != str(args.new_id) and row['uid'] == uid_text for n, row in units.items()):
            raise UpdateError("This board is already recorded at another ID")
        result = configure(port, args.address, args.new_id, width, expected_uid)
        result.update(application_sha256=hashlib.sha256(app).hexdigest(), image_crc=f"{manifest[2]:08X}",
                      verified_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    if any(n != str(args.new_id) and row['uid'] == result['uid'] for n, row in units.items()):
        raise UpdateError("This MCU is already recorded at another ID; inspect ledger")
    units[str(args.new_id)] = result
    temp = ledger.with_suffix('.tmp')
    temp.write_text(json.dumps(units, indent=2) + '\n')
    temp.replace(ledger)
    print("Verified:", json.dumps(result), flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, UpdateError, TimeoutError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Commissioning stopped: {error}")
