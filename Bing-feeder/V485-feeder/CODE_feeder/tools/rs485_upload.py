#!/usr/bin/env python3
"""Upload a V485 application to explicit EEPROM destination ID(s), never broadcast.

Uses pyserial, already installed with PlatformIO. Run --help or --self-check.
The initial bootloader must be installed separately over SWD; see BOOTLOADER.md.
"""
import argparse
from pathlib import Path
import struct
import sys
import time
import zlib

APP_START = 0x08002000
APP_MAX = 56 * 1024
TAG_OFFSET = 0x200
CHUNK = 32


def crc32(data):
    return zlib.crc32(data) & 0xFFFFFFFF


def packet(address, body):
    """CRC covers the destination and ASCII body, not the final separator/LF."""
    if not 0 <= address <= 99:
        raise ValueError("Destination ID must be 0..99")
    text = f"B{address:02d} {body}".encode("ascii")
    return text + f" {crc32(text):08X}\n".encode("ascii")


def decode_packet(raw, address):
    """Ignore noise, damaged packets and other destinations, including echoes."""
    if len(raw) > 128 or not raw.endswith(b"\n"):
        return None
    text = raw[:-1].removesuffix(b"\r")
    prefix = f"B{address:02d} ".encode("ascii")
    if not text.startswith(prefix) or len(text) < 14 or text[-9:-8] != b" ":
        return None
    try:
        expected = int(text[-8:], 16)
        if len(text[-8:]) != 8 or any(ch not in b"0123456789abcdefABCDEF" for ch in text[-8:]):
            return None
        if crc32(text[:-9]) != expected:
            return None
        return text[4:-9].decode("ascii")
    except (ValueError, UnicodeDecodeError):
        return None


def inspect_image(data):
    """Refuse loader binaries, old unrelocated firmware and impossible vectors."""
    if not TAG_OFFSET + 16 <= len(data) <= APP_MAX:
        raise ValueError(f"Application size must be {TAG_OFFSET + 16}..{APP_MAX} bytes")
    stack, reset = struct.unpack_from("<II", data)
    magic, variant, base = struct.unpack_from("<8sII", data, TAG_OFFSET)
    if magic != b"V485APP\0" or variant not in (1, 2) or base != APP_START:
        raise ValueError("Not a V485 bootloader-compatible application (tag/variant/base)")
    if not 0x20000000 < stack <= 0x20005000 or stack % 8:
        raise ValueError("Invalid STM32F103C8 initial stack pointer")
    if not reset & 1 or not APP_START <= reset & ~1 < APP_START + len(data):
        raise ValueError("Reset vector is outside this application's Thumb code")
    return variant, len(data), crc32(data)


class UpdateError(Exception):
    pass


class Link:
    """One request in flight. Only idempotent loader requests are retried."""
    def __init__(self, port, address):
        self.port, self.address = port, address

    def request(self, body, accepted, timeout=1.0, attempts=3, expected=None):
        for _ in range(attempts):
            self.port.write(packet(self.address, body))
            self.port.flush()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                response = decode_packet(self.port.read_until(b"\n", 129), self.address)
                if response is None:
                    continue
                if response.startswith("ERROR "):
                    raise UpdateError(f"ID {self.address}: {response}")
                if response.split(" ", 1)[0] in accepted and (expected is None or response == expected):
                    return response
        raise TimeoutError(f"ID {self.address}: no valid reply to {body.split()[0]}")


def fields(response, label, count):
    parts = response.split(" ")
    if parts[0] != label or len(parts) != count + 1:
        raise UpdateError(f"Unexpected reply: {response}")
    try:
        if any(len(part) != 8 or any(ch not in "0123456789abcdefABCDEF" for ch in part)
               for part in parts[1:]):
            raise ValueError()
        return tuple(int(part, 16) for part in parts[1:])
    except ValueError as error:
        raise UpdateError(f"Invalid reply values: {response}") from error


def enter_loader(link, variant):
    try:
        ready = link.request("HELLO", {"READY"}, attempts=1)
    except TimeoutError:
        # Check width BEFORE requesting a running application to stop/reset.
        app = fields(link.request("INFO", {"APP"}, timeout=3, attempts=2), "APP", 3)
        if app[0] != variant:
            raise UpdateError(f"ID {link.address}: feeder/image width mismatch")
        try:
            link.request("BOOT", {"RESET", "READY"}, attempts=1)
        except TimeoutError:
            pass  # RESET acknowledgement can be lost; HELLO confirms transition.
        ready = link.request("HELLO", {"READY"}, timeout=2, attempts=3)
    if fields(ready, "READY", 3) != (variant, APP_START, APP_MAX):
        raise UpdateError(f"ID {link.address}: loader/image variant or memory layout mismatch")


def upload(link, data):
    variant, size, checksum = inspect_image(data)
    enter_loader(link, variant)
    manifest = f"BEGIN {variant:08X} {size:08X} {checksum:08X}"
    response = link.request(manifest, {"OK"}, timeout=6)
    offset, = fields(response, "OK", 1)
    if offset > size or (offset != size and offset % CHUNK):
        raise UpdateError(f"ID {link.address}: invalid resume offset {offset}")
    shown = -1
    while offset < size:
        end = min(offset + CHUNK, size)
        response = link.request(f"DATA {offset:08X} {data[offset:end].hex().upper()}", {"OK"},
                                expected=f"OK {end:08X}")
        confirmed, = fields(response, "OK", 1)
        # A stale/delayed OK must never silently skip data or claim progress.
        if confirmed != end:
            raise UpdateError(f"ID {link.address}: expected offset {end}, got {confirmed}; rerun upload")
        offset = end
        percent = offset * 100 // size
        if percent // 10 != shown:
            shown = percent // 10
            print(f"ID {link.address}: {percent}%", flush=True)
    try:
        # END is sent once. After commit the target jumps into its application;
        # retries go to INFO instead of blindly assuming the ACK was received.
        done = link.request(f"END {checksum:08X}", {"DONE"}, timeout=3, attempts=1)
        if fields(done, "DONE", 1) != (checksum,):
            raise UpdateError(f"ID {link.address}: final CRC reply mismatch")
    except TimeoutError:
        app = fields(link.request("INFO", {"APP"}, timeout=3, attempts=3), "APP", 3)
        if app != (variant, size, checksum):
            raise UpdateError(f"ID {link.address}: upload completion could not be confirmed")
    print(f"ID {link.address}: verified {size} bytes, CRC32 {checksum:08X}", flush=True)


def address_value(value):
    try:
        address = int(value, 10)
        if not 0 <= address <= 99:
            raise ValueError()
        return address
    except ValueError as error:
        raise argparse.ArgumentTypeError("Set an explicit destination feeder ID, 0..99") from error


def self_check():
    """Offline checks, no serial port, writes or project tests directory."""
    assert crc32(b"123456789") == 0xCBF43926
    encoded = packet(7, "DATA 00000000 01020304")
    assert decode_packet(encoded, 7) == "DATA 00000000 01020304"
    assert decode_packet(encoded, 8) is None
    assert decode_packet(encoded.replace(b"B07", b"B08"), 8) is None
    assert decode_packet(encoded.replace(b"01020304", b"01020305"), 7) is None
    assert decode_packet(encoded[:-1], 7) is None
    image = bytearray(b"\xFF" * 1024)
    struct.pack_into("<II", image, 0, 0x20005000, APP_START + 0x211)
    struct.pack_into("<8sII", image, TAG_OFFSET, b"V485APP\0", 1, APP_START)
    assert inspect_image(image) == (1, 1024, crc32(image))
    for offset, value in ((0, 0x20005008), (4, APP_START - 1), (4, APP_START + 0x210),
                          (TAG_OFFSET + 8, 3), (TAG_OFFSET + 12, 0x08000000)):
        bad = bytearray(image)
        struct.pack_into("<I", bad, offset, value)
        try:
            inspect_image(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Accepted damaged image at {offset}")
    print("Offline destination/CRC/image checks passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", type=Path, help="Application firmware.bin, not the bootloader")
    parser.add_argument("--port", help="Auto-direction USB-RS485 port, e.g. COM5 or /dev/ttyUSB0")
    destinations = parser.add_mutually_exclusive_group()
    destinations.add_argument("--address", type=address_value, help="Destination EEPROM ID, 0..99")
    destinations.add_argument("--addresses", help="Comma-separated unique IDs, updated sequentially")
    parser.add_argument("--inspect", action="store_true", help="Validate/describe firmware without a serial port")
    parser.add_argument("--self-check", action="store_true", help="Run small offline protocol/image checks")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return 0
    if args.firmware is None:
        parser.error("--firmware is required")
    try:
        data = args.firmware.read_bytes()
        variant, size, checksum = inspect_image(data)
        print(f"Image: {'8mm' if variant == 1 else '12/16/24mm'}, {size} bytes, CRC32 {checksum:08X}")
        if args.inspect:
            return 0
        ids = ([address_value(value) for value in args.addresses.split(",")]
               if args.addresses else [args.address] if args.address is not None else [])
        if not args.port or not ids:
            parser.error("Upload requires --port and an explicit --address or --addresses")
        if len(set(ids)) != len(ids):
            parser.error("Destination IDs must be unique")
        # PlatformIO's Python already has pyserial. Plain Python: pip install pyserial.
        import serial
        completed = []
        with serial.Serial(args.port, 9600, timeout=0.15, write_timeout=2) as port:
            port.reset_input_buffer()
            for address in ids:
                print(f"Destination ID {address}: starting", flush=True)
                try:
                    upload(Link(port, address), data)
                except (UpdateError, TimeoutError) as error:
                    raise UpdateError(f"{error}. Completed IDs: {completed}; stopped before remaining IDs") from error
                completed.append(address)
        return 0
    except (OSError, ValueError, UpdateError, TimeoutError, argparse.ArgumentTypeError) as error:
        print(f"Upload failed: {error}", file=sys.stderr)
        return 1
    except ImportError:
        print("pyserial is required; run with PlatformIO's Python or install pyserial", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Upload interrupted. Target remains recoverable in its loader; rerun the same upload.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
