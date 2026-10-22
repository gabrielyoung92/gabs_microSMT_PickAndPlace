#!/usr/bin/env python3
"""Set a V485 feeder ID after selecting menu 01 on its PA4 button.

Use the ESP32-C3 bridge or an auto-direction RS485 adapter. Close OpenPnP first.
Only one commissioning feeder at ID 0 may be connected. No hardware is opened
by --self-check. This tool never sends movement or firmware erase commands.
"""
import argparse
import secrets
import time

from rs485_upload import Link, UpdateError, address_value, decode_packet, fields, packet


def identify(link, nonce, timeout):
    reply = link.request(f"IDENT {nonce:08X}", {"IDENT"}, timeout=timeout,
                         expected=None)
    echoed, *identity, armed = fields(reply, "IDENT", 5)
    if echoed != nonce or armed not in (0, 1):
        raise UpdateError("Unexpected identity reply; assignment cancelled")
    return tuple(identity), armed


def check_unused(port, address, nonce, timeout):
    """Probe application and loader. Any reply/noise prevents assignment.

    Silence only means no responding device was found; an unplugged/offline
    feeder's stored ID cannot be checked. Never infer free from a damaged reply.
    """
    for body in (f"IDENT {nonce:08X}", "HELLO"):
        port.write(packet(address, body))
        port.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = port.read_until(b"\n", 129)
            if not raw:
                continue
            # Some adapters echo our own complete transmission.
            if decode_packet(raw, address) == body:
                continue
            raise UpdateError(f"ID {address} replied, or bus noise was received; choose another ID/check the bus")


def new_id_value(value):
    result = address_value(value)
    if result == 0:
        raise argparse.ArgumentTypeError("New feeder ID must be 1..99; 0 is unassigned")
    return result


def assign(port, address, new_id, timeout=1.0):
    if not 0 <= address <= 99 or not 1 <= new_id <= 99:
        raise ValueError("Current address must be 0..99; new feeder ID must be 1..99")
    port.reset_input_buffer()
    nonce = secrets.randbits(32)
    link = Link(port, address)
    uid, armed = identify(link, nonce, timeout)
    if not armed:
        raise UpdateError("Select menu 01 on the feeder first (it expires after 20 seconds)")
    if address != new_id:
        check_unused(port, new_id, nonce, timeout)
    # Recheck after the occupancy probe: do not use an expired physical selection
    # or an identity that changed while we were waiting.
    checked_uid, armed = identify(link, nonce, timeout)
    if checked_uid != uid or not armed:
        raise UpdateError("Feeder selection changed/expired; assignment cancelled")
    body = "SETID " + " ".join(f"{n:08X}" for n in (nonce, *uid, new_id))
    try:
        link.request(body, {"ID"}, timeout=timeout, attempts=1,
                     expected=f"ID {nonce:08X} {new_id:08X}")
    except TimeoutError:
        # A lost acknowledgement may follow a successful save. Read the new ID
        # and compare the hardware UID; never send SETID a second time.
        pass
    verified_uid, armed = identify(Link(port, new_id), nonce, timeout)
    if verified_uid != uid or armed:
        raise UpdateError("New ID did not confirm the selected hardware; inspect before retrying")
    return uid


def self_check():
    """Exercise the real framing/client/assignment flow against a small bus fake."""
    class Port:
        def __init__(self, occupied=None, lost=False, armed=1, noise=False, fail=False):
            self.address, self.uid, self.armed = 7, (0x11, 0x22, 0x33), armed
            self.occupied, self.lost, self.noise, self.fail = occupied, lost, noise, fail
            self.rx, self.writes, self.saves = [], [], 0

        def reset_input_buffer(self):
            self.rx.clear()

        def flush(self):
            pass

        def read_until(self, *args):
            return self.rx.pop(0) if self.rx else b""

        def write(self, raw):
            self.writes.append(raw)
            address = int(raw[1:3])
            body = decode_packet(raw, address)
            assert body and body.split(" ", 1)[0] not in ("FEED", "BEGIN", "DATA")
            if address != self.address:
                if self.noise:
                    self.rx.append(b"damaged reply\n")
                elif self.occupied == "app" and body.startswith("IDENT "):
                    self.rx.append(packet(address, f"IDENT {body[6:]} 000000AA 000000BB 000000CC 00000000"))
                elif self.occupied == "loader" and body == "HELLO":
                    self.rx.append(packet(address, "READY 00000001 08002000 0000E000"))
                return
            if body.startswith("IDENT "):
                self.rx.append(packet(address, "IDENT " + body[6:] + " " +
                                      " ".join(f"{n:08X}" for n in (*self.uid, self.armed))))
            elif body.startswith("SETID "):
                values = tuple(int(n, 16) for n in body.split()[1:])
                assert values[1:4] == self.uid and self.armed
                self.saves += 1
                if self.fail:
                    self.rx.append(packet(address, "ERROR EEPROM"))
                    return
                self.address, self.armed = values[4], 0
                if not self.lost:
                    self.rx.append(packet(address, f"ID {values[0]:08X} {self.address:08X}"))

    for new_id in (1, 7, 99):
        for lost in (False, True):
            port = Port(lost=lost)
            assert assign(port, 7, new_id, timeout=0.001) == port.uid
            assert port.address == new_id and port.saves == 1
    port = Port()
    try:
        assign(port, 7, 0)
    except ValueError:
        assert not port.writes and not port.saves
    else:
        raise AssertionError("ID 0 accepted")
    port = Port()
    port.address = 0
    assert assign(port, 0, 1, timeout=0.001) == port.uid and port.address == 1
    for options in ({"occupied": "app"}, {"occupied": "loader"}, {"noise": True}, {"armed": 0}, {"fail": True}):
        port = Port(**options)
        try:
            assign(port, 7, 8, timeout=0.001)
        except UpdateError:
            assert port.address == 7 and port.saves == int(bool(options.get("fail")))
        else:
            raise AssertionError(options)
    print("ID assignment: identity, local arming, occupied app/loader, noise, save failure and lost ACK checks passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Controller/adapter serial port, e.g. COM5")
    parser.add_argument("--address", type=address_value, help="Current feeder ID")
    parser.add_argument("--new-id", type=new_id_value, help="Requested operating ID, 1..99")
    parser.add_argument("--self-check", action="store_true", help="Check offline; no serial port opened")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    if not args.port or args.address is None or args.new_id is None:
        parser.error("--port, --address and --new-id are required")
    try:
        import serial
        with serial.Serial(args.port, 9600, timeout=0.1, write_timeout=2) as port:
            time.sleep(2)  # Allow the USB controller to restart after opening.
            uid = assign(port, args.address, args.new_id)
        print(f"Saved ID {args.new_id:02d}; hardware UID {''.join(f'{n:08X}' for n in uid)} verified")
    except (ImportError, OSError, ValueError, UpdateError, TimeoutError) as error:
        parser.exit(1, f"ID assignment failed: {error}\n")


if __name__ == "__main__":
    main()
