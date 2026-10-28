#!/usr/bin/env python3
"""Read/set 0.1.1 motor/switch options. Never feeds or uploads firmware."""
import argparse
import secrets

from assign_id import identify
from rs485_upload import Link, UpdateError, address_value, fields


def read_options(link, nonce):
    result = fields(link.request(f"CONFIG {nonce:08X}", {"CONFIG"}), "CONFIG", 4)
    if result[0] != nonce or any(value not in (0, 1) for value in result[1:]):
        raise UpdateError("Invalid configuration reply")
    return result[1:]


def configure(port, address, options=None):
    nonce = secrets.randbits(32)
    link = Link(port, address)
    uid, _ = identify(link, nonce, 1)
    before = read_options(link, nonce)
    if options is None:
        return uid, before
    if len(options) != 3 or any(value not in (0, 1) for value in options):
        raise ValueError("Three boolean configuration values required")
    checked_uid, _ = identify(link, nonce, 1)
    if checked_uid != uid:
        raise UpdateError("Feeder identity changed")
    body = "SETCONFIG " + " ".join(f"{v:08X}" for v in (nonce, *uid, *options))
    expected = "CONFIGSET " + " ".join(f"{v:08X}" for v in (nonce, *options))
    try:
        link.request(body, {"CONFIGSET"}, attempts=1, expected=expected)
    except TimeoutError:
        pass  # Verify an uncertain save; never automatically repeat the write.
    actual_uid, _ = identify(link, nonce, 1)
    actual = read_options(link, nonce)
    if actual_uid != uid or actual != tuple(options):
        raise UpdateError("Configuration did not verify on the selected board")
    return uid, actual


def events_for_pitch(pitch_mm, step_um):
    from decimal import Decimal, InvalidOperation
    try:
        pitch = Decimal(str(pitch_mm))
        if not pitch.is_finite() or pitch <= 0 or step_um not in (2000, 4000):
            raise ValueError("Pitch must be positive and feeder step must be valid")
        events = pitch * 1000 / step_um
        if events != events.to_integral_value() or not 1 <= events <= 99:
            raise ValueError(f"Pitch must be an exact multiple of {step_um / 1000:g} mm, within 1..99 sensor events")
        return int(events)
    except InvalidOperation as error:
        raise ValueError("Invalid item pitch") from error


def set_count(port, address, count):
    if not 1 <= count <= 99:
        raise ValueError("Default count must be 1..99")
    link = Link(port, address)
    nonce = secrets.randbits(32)
    uid, _ = identify(link, nonce, 1)
    body = "SETCOUNT " + " ".join(f"{v:08X}" for v in (nonce, *uid, count))
    try:
        link.request(body, {"COUNTSET"}, attempts=1,
                     expected=f"COUNTSET {nonce:08X} {count:08X}")
    except TimeoutError:
        pass
    actual_uid, _ = identify(link, nonce, 1)
    result = fields(link.request(f"TYPE {nonce:08X}", {"TYPE"}), "TYPE", 4)
    if actual_uid != uid or result[0] != nonce or result[2] != count:
        raise UpdateError("Default count did not verify on the selected board")
    return result[1:]


def self_check():
    from rs485_upload import decode_packet, packet

    class Port:
        def __init__(self, armed=True, lost=False):
            self.rx, self.options, self.saves = [], (0, 0, 0), 0
            self.armed, self.lost = armed, lost
            self.count = 1

        def write(self, raw):
            body = decode_packet(raw, 9)
            parts = body.split()
            label, nonce = parts[:2]
            self.rx.append(raw)  # Exercise local adapter echo filtering.
            if label == 'IDENT':
                reply = f'IDENT {nonce} 00000011 00000022 00000033 {int(self.armed):08X}'
            elif label == 'CONFIG':
                reply = 'CONFIG ' + nonce + ''.join(f' {v:08X}' for v in self.options)
            elif label == 'TYPE':
                reply = f'TYPE {nonce} 00000008 {self.count:08X} 000007D0'
            elif label == 'SETCOUNT':
                assert parts[2:5] == ['00000011', '00000022', '00000033']
                self.count = int(parts[5], 16)
                self.saves += 1
                if self.lost:
                    return
                reply = f'COUNTSET {nonce} {self.count:08X}'
            elif label == 'SETCONFIG':
                assert parts[2:5] == ['00000011', '00000022', '00000033']
                self.options = tuple(int(v, 16) for v in parts[5:])
                self.saves += 1
                if self.lost:
                    return
                reply = 'CONFIGSET ' + nonce + ''.join(f' {v:08X}' for v in self.options)
            else:
                raise AssertionError(body)
            self.rx.append(packet(9, reply))

        def flush(self):
            pass

        def read_until(self, *_):
            return self.rx.pop(0) if self.rx else b''

    port = Port()
    assert configure(port, 9)[1] == (0, 0, 0) and port.saves == 0
    for lost in (False, True):
        port = Port(lost=lost)
        assert configure(port, 9, (1, 0, 1))[1] == (1, 0, 1) and port.saves == 1
    port = Port(armed=False)
    assert configure(port, 9, (1, 1, 1))[1] == (1, 1, 1) and port.saves == 1
    assert events_for_pitch('4', 2000) == 2
    assert events_for_pitch('12', 4000) == 3
    for pitch in ('6', 'NaN', '-4'):
        try:
            events_for_pitch(pitch, 4000)
        except ValueError:
            pass
        else:
            raise AssertionError('Unresolvable/invalid pitch accepted')
    for lost in (False, True):
        port = Port(armed=False, lost=lost)
        assert set_count(port, 9, 2) == (8, 2, 2000) and port.saves == 1
    print('Configuration client checks passed: direct bus save, echo, UID, verification, lost ACK without replay')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port')
    parser.add_argument('--address', type=address_value)
    parser.add_argument('--feed', choices=('normal', 'reversed'))
    parser.add_argument('--peel', choices=('normal', 'reversed'))
    parser.add_argument('--switch', choices=('nc', 'no'))
    pitch_group = parser.add_mutually_exclusive_group()
    pitch_group.add_argument('--pitch-mm', help='Item pitch, must be an exact multiple of this feeder sensor step')
    pitch_group.add_argument('--count', type=int, help='Saved default optical events, 1..99; 8 mm type: two events = nominal 4 mm')
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    if args.port is None or args.address is None:
        parser.error('--port and --address are required')
    values = (args.feed, args.peel, args.switch)
    if any(v is not None for v in values) and not all(v is not None for v in values):
        parser.error('Set --feed, --peel and --switch together, or omit all three to read')
    if args.count is not None and not 1 <= args.count <= 99:
        parser.error("--count must be 1..99")
    options = None if args.feed is None else (int(args.feed == 'reversed'), int(args.peel == 'reversed'), int(args.switch == 'no'))
    import serial
    with serial.Serial(args.port, 115200, timeout=.05, write_timeout=2,
                       **({'exclusive': True} if __import__('os').name == 'posix' else {})) as port:
        port.reset_input_buffer()
        count = args.count
        if args.pitch_mm is not None:
            nonce = secrets.randbits(32)
            typed = fields(Link(port, args.address).request(f'TYPE {nonce:08X}', {'TYPE'}), 'TYPE', 4)
            if typed[0] != nonce:
                raise UpdateError('Unexpected TYPE reply')
            count = events_for_pitch(args.pitch_mm, typed[3])
        uid, actual = configure(port, args.address, options)
        travel = set_count(port, args.address, count) if count is not None else None
    print('UID:', ' '.join(f'{v:08X}' for v in uid))
    print(f"Feed: {('normal', 'reversed')[actual[0]]}; peel: {('normal', 'reversed')[actual[1]]}; switch: {('NC', 'NO')[actual[2]]}")
    if travel is not None:
        print(f"Saved default: {travel[1]} events; nominal travel {travel[1] * travel[2] / 1000:g} mm ({travel[0]} mm feeder)")
    if options is not None:
        print('EEPROM verified. Settings are active; no button selection required.')


if __name__ == '__main__':
    main()
