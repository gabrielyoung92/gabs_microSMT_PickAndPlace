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

# Upload sequence: validate file -> find this ID -> enter loader -> BEGIN ->
# DATA chunks -> END verification. Batch mode finishes one ID before the next.
# The ESP32-C3 bridge or adapter handles RS485 direction; this script never broadcasts or changes
# the feeder's EEPROM ID. The loader itself is installed separately over SWD.

# Keep these values in step with src/boot.h and the application linker script.
APP_START = 0x08002000  # First 8 KB of the 64 KB flash belongs to the loader.
APP_MAX = 56 * 1024    # Remaining flash available to the application.
TAG_OFFSET = 0x200    # Fixed 16-byte identity tag, after the vector table.
CHUNK = 32            # Binary bytes per DATA request; encoded as 64 hex digits.


def crc32(data):
    """Return the unsigned IEEE CRC32 used by both packet and image checks."""
    # Matches Boot_Crc32() in the feeder. This detects corruption, not authorship.
    return zlib.crc32(data) & 0xFFFFFFFF


def packet(address, body):
    """Encode one request as Bdd <body> <CRC32> LF for destination ID dd.

    body contains only the command and its fields. The checksum covers the
    destination as well as the body, preventing a damaged ID from redirecting it.
    """
    if not 0 <= address <= 99:
        raise ValueError("Destination ID must be 0..99")
    # ID is two decimal digits; CRC is eight hex digits. The final separating
    # space, checksum itself and LF are excluded from the checksum calculation.
    text = f"B{address:02d} {body}".encode("ascii")
    return text + f" {crc32(text):08X}\n".encode("ascii")


def decode_packet(raw, address):
    """Return the ASCII body of a complete, CRC-valid packet for this ID.

    Return None for fragments, noise, other destinations or invalid checksums.
    A local adapter echo may decode too; request() filters command echoes by
    accepting only the expected reply labels/body.
    """
    # read_until() can return a fragment on timeout or at its byte limit. A
    # fragment is never interpreted as a complete acknowledgement.
    if len(raw) > 128 or not raw.endswith(b"\n"):
        return None
    # Accept LF or CRLF, preserving all other bytes for the exact CRC check.
    text = raw[:-1].removesuffix(b"\r")
    prefix = f"B{address:02d} ".encode("ascii")
    if not text.startswith(prefix) or len(text) < 14 or text[-9:-8] != b" ":
        return None
    try:
        # Slice layout: four-byte Bdd prefix, body, space, eight-digit CRC.
        # Check the spelling too: int(..., 16) alone accepts signs/whitespace.
        expected = int(text[-8:], 16)
        if len(text[-8:]) != 8 or any(ch not in b"0123456789abcdefABCDEF" for ch in text[-8:]):
            return None
        if crc32(text[:-9]) != expected:
            return None
        return text[4:-9].decode("ascii")
    except (ValueError, UnicodeDecodeError):
        return None


def inspect_image(data):
    """Validate application bytes; return (width variant, byte count, CRC32).

    Reject loader files, old firmware linked at flash base and invalid vectors
    before opening a serial port or allowing an erase. The device repeats these
    checks against the received image before it marks the application valid.
    """
    if not TAG_OFFSET + 16 <= len(data) <= APP_MAX:
        raise ValueError(f"Application size must be {TAG_OFFSET + 16}..{APP_MAX} bytes")
    # Cortex-M vectors begin with initial stack pointer and reset-handler
    # address. Both the vectors and the identity tag use little-endian words.
    stack, reset = struct.unpack_from("<II", data)
    magic, variant, base = struct.unpack_from("<8sII", data, TAG_OFFSET)
    # Variant 1 = 8 mm; 2 = shared 12/16/24 mm firmware. The fixed base rejects
    # unrelocated images even if their file size would otherwise fit.
    if magic != b"V485APP\0" or variant not in (1, 2) or base != APP_START:
        raise ValueError("Not a V485 bootloader-compatible application (tag/variant/base)")
    # F103C8 has 20 KB RAM. The stack may start at its upper boundary because
    # it grows down; require the normal eight-byte stack alignment.
    if not 0x20000000 < stack <= 0x20005000 or stack % 8:
        raise ValueError("Invalid STM32F103C8 initial stack pointer")
    # Bit 0 selects Thumb execution and must be set. Clear it only when checking
    # that the handler's actual address lies inside the supplied image.
    if not reset & 1 or not APP_START <= reset & ~1 < APP_START + len(data):
        raise ValueError("Reset vector is outside this application's Thumb code")
    return variant, len(data), crc32(data)


class UpdateError(Exception):
    """A device/protocol failure that stops this upload and any remaining IDs."""
    pass


class Link:
    """Request/reply connection for one ID on an already-open serial port.

    Keep one request in flight. Callers use one attempt for BOOT/END; read-only
    requests and retry-safe BEGIN/DATA exchanges may use multiple attempts.
    """
    def __init__(self, port, address):
        """Bind the serial connection to its explicit destination EEPROM ID."""
        self.port, self.address = port, address

    def request(self, body, accepted, timeout=1.0, attempts=3, expected=None):
        """Send body and return an accepted reply, or raise on error/timeout.

        accepted is a set of reply labels such as READY or OK. expected can
        additionally require the whole body, used for the exact next DATA offset.
        timeout is seconds per attempt; attempts controls whether retransmission
        is allowed. A valid ERROR reply aborts immediately instead of retrying.
        """
        for _ in range(attempts):
            self.port.write(packet(self.address, body))
            # Finish queued transmission; this does not acknowledge delivery.
            self.port.flush()
            # A monotonic deadline is unaffected by Windows/system clock changes.
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                # Read one byte beyond our 128-byte reply limit so an oversized
                # line is rejected. Ignore invalid/partial packets until timeout.
                response = decode_packet(self.port.read_until(b"\n", 129), self.address)
                if response is None:
                    continue
                if response.startswith("ERROR "):
                    raise UpdateError(f"ID {self.address}: {response}")
                # Matching a DATA reply's full offset ignores delayed duplicate
                # OKs from earlier chunks. Echoes have command, not reply, labels.
                if response.split(" ", 1)[0] in accepted and (expected is None or response == expected):
                    return response
        raise TimeoutError(f"ID {self.address}: no valid reply to {body.split()[0]}")


def fields(response, label, count):
    """Parse exactly count eight-digit hex fields after label; return a tuple.

    CRC validity does not guarantee the expected reply shape. Missing, extra or
    malformed fields are protocol errors, not usable progress/identity values.
    """
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
    """Find the loader, or ask a matching running application to enter it.

    Return only after READY confirms width, application base and capacity. Busy
    feeds and device errors propagate to the caller; no erase happens here.
    """
    try:
        # A previous upload/reset may already have left this ID in recovery.
        ready = link.request("HELLO", {"READY"}, attempts=3)
    except TimeoutError:
        # Check width BEFORE requesting a running application to stop/reset.
        app = fields(link.request("INFO", {"APP"}, timeout=3, attempts=2), "APP", 3)
        if app[0] != variant:
            raise UpdateError(f"ID {link.address}: feeder/image width mismatch")
        try:
            # BOOT records the request and resets the application. Send it once;
            # do not keep resetting a device merely because RESET was not heard.
            link.request("BOOT", {"RESET", "READY"}, attempts=1)
        except TimeoutError:
            pass  # RESET acknowledgement can be lost; HELLO confirms transition.
        ready = link.request("HELLO", {"READY"}, timeout=2, attempts=3)
    # Refuse a different width or loader memory map BEFORE sending BEGIN.
    if fields(ready, "READY", 3) != (variant, APP_START, APP_MAX):
        raise UpdateError(f"ID {link.address}: loader/image variant or memory layout mismatch")


def upload(link, data):
    """Upload one application to link's ID and confirm its final image CRC.

    BEGIN/DATA use stop-and-wait retries. The loader validates the full image
    and commits EEPROM metadata on END. Failures raise, stopping the batch.
    """
    # Check here too so callers outside main() cannot bypass image validation.
    variant, size, checksum = inspect_image(data)
    enter_loader(link, variant)
    manifest = f"BEGIN {variant:08X} {size:08X} {checksum:08X}"
    # BEGIN is the destructive step: the loader marks the app invalid before
    # erasing its pages. Allow extra time for EEPROM writes and flash erasure.
    # An identical BEGIN retry keeps an existing live session's progress.
    response = link.request(manifest, {"OK"}, timeout=6)
    offset, = fields(response, "OK", 1)
    # Progress is in loader RAM, not persistent resume storage. A target reset
    # restarts at zero. Otherwise expect chunk boundaries, or an already-complete
    # image whose final chunk may be short/odd-sized.
    if offset > size or (offset != size and offset % CHUNK):
        raise UpdateError(f"ID {link.address}: invalid resume offset {offset}")
    shown = -1
    while offset < size:
        end = min(offset + CHUNK, size)
        # Offset is relative to APP_START, never an arbitrary flash address.
        # The receiver handles halfword padding for a final odd-sized payload.
        link.request(f"DATA {offset:08X} {data[offset:end].hex().upper()}", {"OK"},
                     expected=f"OK {end:08X}")
        offset = end
        percent = offset * 100 // size
        # Print approximately every ten percent, not one line per 32-byte chunk.
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
        # DONE can be lost while the newly committed application starts. INFO
        # must match width, length AND CRC; an unrelated/old app is not success.
        app = fields(link.request("INFO", {"APP"}, timeout=3, attempts=3), "APP", 3)
        if app != (variant, size, checksum):
            raise UpdateError(f"ID {link.address}: upload completion could not be confirmed")
    print(f"ID {link.address}: verified {size} bytes, CRC32 {checksum:08X}", flush=True)


def address_value(value):
    """Validate a CLI destination, including PlatformIO's REQUIRED placeholder.

    ID 0 is permitted for commissioning but is never selected implicitly.
    """
    try:
        address = int(value, 10)
        if not 0 <= address <= 99:
            raise ValueError()
        return address
    except ValueError as error:
        raise argparse.ArgumentTypeError("Set an explicit destination feeder ID, 0..99") from error


def self_check():
    """Offline checks, no serial port, writes or project tests directory."""
    # Standard CRC test vector, then destination/data corruption and framing.
    assert crc32(b"123456789") == 0xCBF43926
    encoded = packet(7, "DATA 00000000 01020304")
    assert decode_packet(encoded, 7) == "DATA 00000000 01020304"
    assert decode_packet(encoded, 8) is None
    assert decode_packet(encoded.replace(b"B07", b"B08"), 8) is None
    assert decode_packet(encoded.replace(b"01020304", b"01020305"), 7) is None
    assert decode_packet(encoded[:-1], 7) is None
    # Synthetic header only: enough to exercise validation, not runnable code.
    image = bytearray(b"\xFF" * 1024)
    struct.pack_into("<II", image, 0, 0x20005000, APP_START + 0x211)
    struct.pack_into("<8sII", image, TAG_OFFSET, b"V485APP\0", 1, APP_START)
    assert inspect_image(image) == (1, 1024, crc32(image))
    # Mutate stack range, reset range/Thumb bit, variant and linked base in turn.
    # Each must fail even though the remaining header still looks valid.
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
    # One lost READY must retry HELLO, not send application-only INFO to a loader.
    class LostHelloPort:
        def __init__(self):
            self.requests, self.reply = [], b""

        def write(self, data):
            self.requests.append(decode_packet(data, 7))
            assert self.requests[-1] == "HELLO"
            if len(self.requests) > 1:
                self.reply = packet(7, f"READY 00000001 {APP_START:08X} {APP_MAX:08X}")

        def flush(self):
            pass

        def read_until(self, *args):
            reply, self.reply = self.reply, b""
            return reply

    class FastLink(Link):
        def request(self, body, accepted, **kwargs):
            kwargs['timeout'] = 0.03
            return super().request(body, accepted, **kwargs)

    port = LostHelloPort()
    enter_loader(FastLink(port, 7), 1)
    assert port.requests == ['HELLO', 'HELLO']
    print("Offline destination/CRC/image checks passed")


def main():
    """Validate CLI/file, then inspect offline or update explicit IDs in order.

    Return 0 on success, 1 for upload/runtime failure, or 130 after Ctrl+C.
    argparse separately exits with 2 for invalid command-line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", type=Path, help="Application firmware.bin, not the bootloader")
    parser.add_argument("--port", help="ESP32-C3 controller or auto-direction USB-RS485 port, e.g. COM5")
    destinations = parser.add_mutually_exclusive_group()
    destinations.add_argument("--address", type=address_value, help="Destination EEPROM ID, 0..99")
    destinations.add_argument("--addresses", help="Comma-separated unique IDs, updated sequentially")
    parser.add_argument("--inspect", action="store_true", help="Validate/describe firmware without a serial port")
    parser.add_argument("--self-check", action="store_true", help="Run small offline protocol/image checks")
    args = parser.parse_args()
    # Offline modes run before importing pyserial or opening any serial port.
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
        # Preserve the requested batch order. Validate the entire list before
        # opening the port; never silently fall back to destination zero.
        ids = ([address_value(value) for value in args.addresses.split(",")]
               if args.addresses else [args.address] if args.address is not None else [])
        if not args.port or not ids:
            parser.error("Upload requires --port and an explicit --address or --addresses")
        # This catches duplicate CLI entries, not duplicate physical node IDs.
        # The connected feeders must already have unique EEPROM IDs.
        if len(set(ids)) != len(ids):
            parser.error("Destination IDs must be unique")
        # PlatformIO's Python already has pyserial. Plain Python: pip install pyserial.
        import serial
        completed = []
        with serial.Serial(args.port, 115200, timeout=0.15, write_timeout=2) as port:
            # Discard old adapter/startup bytes once, before starting. Do not
            # flush receive data between chunks: a valid ACK may already be queued.
            port.reset_input_buffer()
            for address in ids:
                print(f"Destination ID {address}: starting", flush=True)
                try:
                    upload(Link(port, address), data)
                # Finish/verify this ID before the next. Stop on the first
                # failure and report exactly which earlier IDs were completed.
                except (UpdateError, TimeoutError) as error:
                    raise UpdateError(f"{error}. Completed IDs: {completed}; stopped before remaining IDs") from error
                completed.append(address)
        return 0
    # File, serial and protocol failures get a concise CLI error and nonzero
    # status. The serial context manager closes the port before reaching here.
    except (OSError, ValueError, UpdateError, TimeoutError, argparse.ArgumentTypeError) as error:
        print(f"Upload failed: {error}", file=sys.stderr)
        return 1
    except ImportError:
        print("pyserial is required; run with PlatformIO's Python or install pyserial", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        # After BEGIN, an interrupted transfer leaves the target in its loader;
        # rerunning the upload retries/restarts it rather than booting a partial app.
        print("Upload interrupted. Target remains recoverable in its loader; rerun the same upload.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
