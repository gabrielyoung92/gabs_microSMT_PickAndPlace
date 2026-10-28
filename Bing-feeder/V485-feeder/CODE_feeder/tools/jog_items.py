#!/usr/bin/env python3
"""Advance/retract whole items using the saved event count per item. Peel stays off.

Close the USB host first. This tool owns the bus until the single item move finishes.
Movement is never retried. Sensor counts measure nominal travel, not absolute
position: direction changes/backlash and actual tape motion need bench validation.
"""
import argparse
import secrets
import time

from assign_id import identify
from rs485_upload import Link, UpdateError, address_value, decode_packet, fields, packet


def plan(items, width, per_item, step_um):
    if not isinstance(items, int) or not 1 <= items <= 10000:
        raise ValueError('Items must be 1..10000')
    if width not in (8, 12, 16, 24) or not 1 <= per_item <= 99 or step_um != (2000 if width == 8 else 4000):
        raise UpdateError('Invalid feeder type/default event count/step')
    if items * per_item > 10000:
        raise ValueError('This move exceeds the firmware limit of 10000 sensor events')
    return items * per_item


def motion_reply(port, address, tokens, deadline):
    while time.monotonic() < deadline:
        body = decode_packet(port.read_until(b'\n', 129), address)
        if body is None:
            continue
        label = body.split(' ', 1)[0]
        if label == 'ERROR':
            raise UpdateError(body)
        if label not in {'ACCEPT', 'RUNNING', 'DONE', 'BUSY', 'FAULT', 'UNKNOWN'}:
            continue
        try:
            if fields(body, label, 2) == tokens:
                return label
        except UpdateError:
            continue
    return None


def stop(port, address):
    nonce = secrets.randbits(32)
    return Link(port, address).request(f'STOP {nonce:08X}', {'STOPPED'},
                                       attempts=1, expected=f'STOPPED {nonce:08X}')


def jog(port, address, items, retract=False, execute=True, progress=print, timeout=None):
    link = Link(port, address)
    nonce = secrets.randbits(32)
    uid, _ = identify(link, nonce, 1)
    typed = fields(link.request(f'TYPE {nonce:08X}', {'TYPE'}), 'TYPE', 4)
    if typed[0] != nonce:
        raise UpdateError('Unexpected TYPE reply')
    width, per_item, step_um = typed[1:]
    events = plan(items, width, per_item, step_um)
    progress(f"{'Retract' if retract else 'Advance'} {items} items; {per_item * step_um / 1000:g} mm/item; nominal {items * per_item * step_um / 1000:g} mm; one request ({events} events)")
    if not execute:
        return 0
    checked_uid, _ = identify(link, nonce, 1)
    checked_type = fields(link.request(f'TYPE {nonce:08X}', {'TYPE'}), 'TYPE', 4)
    if checked_uid != uid or checked_type != typed:
        raise UpdateError('Feeder identity/pitch changed; no movement sent')
    tokens = (secrets.randbits(32), secrets.randbits(32))
    text = f'{tokens[0]:08X} {tokens[1]:08X}'
    # Firmware total bound is 2 s + 1 s/event; allow another 2 s for replies.
    deadline = time.monotonic() + (timeout if timeout is not None else 4 + events)
    try:
        # Exactly one motion write. Lost replies only cause read-only STATUS.
        port.write(packet(address, f'JOG {text} {int(retract):08X} {items:08X}'))
        port.flush()
        result = motion_reply(port, address, tokens, min(deadline, time.monotonic() + .3))
        while result != 'DONE':
            if result in {'BUSY', 'FAULT', 'UNKNOWN'}:
                raise UpdateError(f'{result}; movement not confirmed')
            if time.monotonic() >= deadline:
                raise TimeoutError('Movement completion timeout')
            port.write(packet(address, f'STATUS {text}'))
            port.flush()
            result = motion_reply(port, address, tokens, min(deadline, time.monotonic() + .3))
            if result in {None, 'ACCEPT', 'RUNNING'}:
                time.sleep(.03)
    except KeyboardInterrupt:
        try:
            stop(port, address)
            progress('Stop acknowledged; both motors disabled, E4 latched until reset')
        except (OSError, UpdateError, TimeoutError):
            progress('Stop could not be confirmed; movement outcome unknown')
        raise
    except (OSError, UpdateError, TimeoutError) as error:
        raise UpdateError(f'Movement outcome unconfirmed; not retried: {error}') from error
    progress(f'Confirmed {items}/{items} items')
    return items


def self_check():
    class Port:
        def __init__(self, per_item=2, width=8, lost=False, fault=False, interrupt=False):
            self.rx, self.moves = [], []
            self.per_item, self.width = per_item, width
            self.lost, self.fault = lost, fault
            self.interrupt, self.interrupted, self.stops = interrupt, False, 0

        def write(self, raw):
            body = decode_packet(raw, 9)
            values = body.split()
            label = values[0]
            self.rx.append(raw)  # Adapter echo
            if label == 'IDENT':
                reply = f'IDENT {values[1]} 00000011 00000022 00000033 00000000'
            elif label == 'TYPE':
                reply = f'TYPE {values[1]} {self.width:08X} {self.per_item:08X} {(2000 if self.width == 8 else 4000):08X}'
            elif label == 'STOP':
                self.stops += 1
                reply = f'STOPPED {values[1]}'
            elif label == 'JOG':
                self.moves.append(tuple(int(v, 16) for v in values[3:]))
                if self.lost:
                    return
                reply = f'ACCEPT {values[1]} {values[2]}'
            elif label == 'STATUS':
                # A delayed wrong-token result must not finish the current chunk.
                self.rx.append(packet(9, 'DONE 00000000 FFFFFFFF'))
                reply = f"{'FAULT' if self.fault else 'DONE'} {values[1]} {values[2]}"
            else:
                raise AssertionError(body)
            self.rx.append(packet(9, reply))

        def flush(self):
            pass

        def read_until(self, *_):
            if self.interrupt and self.moves and not self.interrupted:
                self.interrupted = True
                raise KeyboardInterrupt
            return self.rx.pop(0) if self.rx else b''

    for lost in (False, True):
        for reverse in (False, True):
            port = Port(lost=lost)
            assert jog(port, 9, 30, reverse, progress=lambda _: None) == 30
            assert port.moves == [(int(reverse), 30)]
    port = Port(per_item=4, width=24)
    assert jog(port, 9, 30, progress=lambda _: None) == 30
    assert port.moves == [(0, 30)]  # 120 events in one request, no 8-bit/99-event limit.
    port = Port()
    assert jog(port, 9, 50, progress=lambda _: None) == 50 and port.moves == [(0, 50)]
    port = Port(fault=True)
    try:
        jog(port, 9, 100, progress=lambda _: None)
    except UpdateError:
        assert len(port.moves) == 1
    else:
        raise AssertionError('Fault continued movement')
    port = Port(interrupt=True)
    try:
        jog(port, 9, 50, progress=lambda _: None)
    except KeyboardInterrupt:
        assert port.stops == 1 and len(port.moves) == 1
    else:
        raise AssertionError('Interrupted motion did not request a stop')
    assert stop(Port(), 9).startswith('STOPPED ')
    port = Port()
    assert jog(port, 9, 30, execute=False, progress=lambda _: None) == 0 and not port.moves
    print('Item jog checks passed: forward/retract, single full-count request, echo, stale tokens, lost ACK without replay, fault stops and plan without movement')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port')
    parser.add_argument('--address', type=address_value)
    parser.add_argument('--stop', action='store_true', help='Stop both motors and latch E4; reset required to resume')
    parser.add_argument('--direction', choices=('advance', 'retract'))
    parser.add_argument('--items', type=int)
    parser.add_argument('--plan', action='store_true', help='Read and describe only; do not move')
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    if args.port is None or args.address is None or (not args.stop and (args.direction is None or args.items is None)):
        parser.error('--port, --address, --direction and --items are required')
    if args.address == 0 or (not args.stop and not 1 <= args.items <= 10000):
        parser.error('Address must be 1..99 and items 1..10000')
    import os
    import serial
    with serial.Serial(args.port, 115200, timeout=.05, write_timeout=2,
                       **({'exclusive': True} if os.name == 'posix' else {})) as port:
        port.reset_input_buffer()
        if args.stop:
            print(stop(port, args.address))
        else:
            jog(port, args.address, args.items, args.direction == 'retract', execute=not args.plan)


if __name__ == '__main__':
    main()
