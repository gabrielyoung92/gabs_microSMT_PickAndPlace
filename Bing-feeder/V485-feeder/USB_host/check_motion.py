#!/usr/bin/env python3
"""Offline motion/HTTP/TCP checks. Temporary listeners; no hardware or profile."""
import http.client
import json
import socket
import threading
import time

import host_service as host
from motion import Motion, MotionError, MotionServer
from simulated_bus import SimulatedBus
from simulated_motion import SimulatedMotion


def rejected(call, kind=(MotionError, ValueError)):
    try:
        call()
    except kind:
        return
    raise AssertionError('Operation unexpectedly accepted')


def until(condition):
    deadline = time.monotonic() + 3
    while not condition():
        assert time.monotonic() < deadline, 'Timed out waiting for test state'
        time.sleep(0.002)


def manual_checks():
    port = SimulatedMotion()
    motion = Motion(port, timeout=0.08)
    try:
        assert not port.writes  # Startup does not reset or command the controller.
        motion.action({'action': 'claim'})
        assert motion.snapshot()['owner'] == 'manual'
        rejected(lambda: motion.action({'action': 'jog', 'axis': 'X', 'distance': 1}))
        rejected(lambda: motion.action({'action': 'home', 'heads_ready': False}))
        assert 'G28' not in port.commands
        port.position.update(A=12.0, B=-8.0)
        motion.action({'action': 'home', 'heads_ready': True})
        assert motion.snapshot()['web_homed']
        for axis, distance in (('X', 10), ('Y', 5), ('Z', -1), ('A', 45), ('B', -30)):
            motion.action({'action': 'jog', 'axis': axis, 'distance': distance})
            assert motion.snapshot()['position'][axis] == distance + {'A':12, 'B':-8}.get(axis, 0)
        assert 'G91' not in port.commands  # Jogging never leaves relative mode active.
        for args in ({'axis': 'X', 'distance': -10.1}, {'axis': 'Y', 'distance': float('nan')},
                     {'axis': None, 'distance': 1}, {'axis': 'A', 'distance': 91},
                     {'axis': 'Z', 'distance': 1, 'speed': 11}):
            before = len([c for c in port.commands if c.startswith('G53')])
            rejected(lambda: motion.action(dict(action='jog', **args)))
            assert len([c for c in port.commands if c.startswith('G53')]) == before
        # Soft bounds use fresh MCS coordinates, never stale work coordinates.
        port.position['X'] = 384
        rejected(lambda: motion.action({'action': 'jog', 'axis': 'X', 'distance': 2}))
        motion.action({'action': 'jog', 'axis': 'X', 'distance': 1})
        assert port.position['X'] == 385
        # A G1 acknowledgement must not finish a web request while M400 waits.
        port.defer_completion = True
        failures = []
        worker = threading.Thread(target=lambda: run_action(motion, {'action':'jog', 'axis':'X', 'distance':-1}, failures))
        worker.start()
        until(lambda: port.target is not None and port.commands[-1] == 'M400')
        assert worker.is_alive() and motion.snapshot()['busy'] and port.position['X'] == 385
        rejected(lambda: motion.action({'action':'release'}))
        port.complete_move()
        worker.join(2)
        assert not worker.is_alive() and not failures and port.position['X'] == 384
        port.defer_completion = False
        motion.action({'action': 'read'})
        assert 'Z_min:1' in motion.snapshot()['endstops']
        for name in motion.snapshot()['outputs']:
            motion.action({'action': 'output', 'name': name, 'enabled': True})
            assert motion.snapshot()['outputs'][name] is True
        motion.action({'action': 'all_off'})
        assert set(motion.snapshot()['outputs'].values()) == {False}
        motion.action({'action': 'disable'})
        assert not motion.snapshot()['web_homed'] and motion.snapshot()['motors'] is False
        motion.action({'action': 'enable'})
        assert motion.snapshot()['motors'] is True
        motion.action({'action': 'release'})
        assert motion.snapshot()['owner'] == 'available'
        # No browser can queue another action behind an in-flight manual command.
        motion.action({'action': 'claim'})
        port.drop_command = 'M400'
        failures = []
        worker = threading.Thread(target=lambda: run_action(motion, {'action': 'read'}, failures))
        worker.start()
        until(lambda: motion.snapshot()['pending'] == 1)
        rejected(lambda: motion.action({'action': 'output', 'name': 'pump', 'enabled': True}))
        motion.action({'action': 'halt'})  # Bypasses the blocked M400 operation.
        worker.join(2)
        assert not worker.is_alive() and failures and port.halted
        assert motion.snapshot()['fault'] and not motion.snapshot()['web_homed']
        rejected(lambda: motion.action({'action': 'release'}))
    finally:
        motion.close()
    # A lost acknowledgement is never retried; reconnect/restart is explicit.
    for failure in ('timeout', 'error', 'disconnect'):
        port = SimulatedMotion()
        motion = Motion(port, timeout=0.05)
        try:
            motion.action({'action': 'claim'})
            if failure == 'timeout':
                port.drop_command = 'M17'
            elif failure == 'error':
                port.error_command = 'M17'
            else:
                port.close()
            rejected(lambda: motion.action({'action': 'enable'}))
            assert port.commands.count('M17') <= 1 and motion.snapshot()['fault']
        finally:
            motion.close()


def run_action(motion, args, failures):
    try:
        motion.action(args)
    except MotionError as error:
        failures.append(str(error))


def network_checks():
    port = SimulatedMotion()
    motion = Motion(port, timeout=0.1)
    stock = host.Stock(':memory:')
    feeders = host.Feeders(SimulatedBus(), stock, [1])
    tcp = MotionServer(0, motion)
    web = host.WebServer(0, feeders, demo=True, motion=motion, motion_port=tcp.server_address[1])
    servers = (tcp, web)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for thread in threads:
        thread.start()
    connection = http.client.HTTPConnection(*web.server_address, timeout=3)
    def request(args=None):
        connection.request('POST' if args is not None else 'GET', '/api/motion' if args is not None else '/api/status',
                           json.dumps(args) if args is not None else None, {'Content-Type': 'application/json'})
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    try:
        status, data = request()
        assert status == 200 and data['motion']['tcp_port'] == tcp.server_address[1]
        with socket.create_connection(tcp.server_address, timeout=2) as client:
            client.settimeout(2)
            until(lambda: motion.snapshot()['owner'] == 'openpnp')
            assert request({'action': 'claim'})[0] == 409
            with socket.create_connection(tcp.server_address, timeout=2) as second:
                assert second.recv(256).startswith(b'error:')
            before = len(port.writes)
            client.sendall(b'G90\r\nM114')
            until(lambda: len(port.writes) > before)
            client.sendall(b'.2\nM400\n')
            raw = b''
            while raw.count(b'ok') < 3:
                raw += client.recv(1024)
            until(lambda: motion.snapshot()['pending'] == 0)
            assert b''.join(port.writes[before:]) == b'G90\r\nM114.2\nM400\n'
            assert raw == b'ok\r\nok MCS: X:0.0000 Y:0.0000 Z:0.0000 A:0.0000 B:0.0000\r\nok\r\n'
            assert request({'action': 'read'})[0] == 409  # No polling injected into the relay.
            # An async driver's command window can be forwarded as a pipeline.
            batch = b''.join(f'G1 X{n} F600\n'.encode() for n in range(100))
            before = len(port.writes)
            client.sendall(batch)
            replies = b''
            while replies.count(b'ok\r\n') < 100:
                replies += client.recv(4096)
            until(lambda: motion.snapshot()['pending'] == 0)
            assert b''.join(port.writes[before:]) == batch
            assert replies == b'ok\r\n' * 100
        until(lambda: motion.snapshot()['owner'] == 'available')
        assert request({'action': 'claim'})[0] == 200
        with socket.create_connection(tcp.server_address, timeout=2) as client:
            assert client.recv(256).startswith(b'error:')
        assert request({'action': 'jog', 'axis': 'X', 'distance': 1})[0] == 409
        assert request({'action': 'home', 'heads_ready': True})[0] == 200
        assert request({'action': 'jog', 'axis': 'X', 'distance': 2})[0] == 200
        assert request()[1]['motion']['position']['X'] == 2
        assert request({'action': 'jog', 'axis': 'XY', 'distance': 2})[0] == 400
        assert request({'action': 'release'})[0] == 200
        # A half-sent line must not later be completed by a browser command.
        with socket.create_connection(tcp.server_address, timeout=2) as client:
            client.sendall(b'G1 X')
            until(lambda: bool(motion.tx_fragment))
        until(lambda: bool(motion.snapshot()['fault']))
        assert request({'action': 'claim'})[0] == 409
    finally:
        connection.close()
        for server in servers:
            server.shutdown()
            server.server_close()
        motion.close()
        stock.close()
        for thread in threads:
            thread.join()


def relay_fault_checks():
    class Client:
        closed = False
        def sendall(self, data):
            pass
        def shutdown(self, how):
            self.closed = True
    for scenario in ('lost_ack', 'reset', 'halt'):
        port, client = SimulatedMotion(), Client()
        motion = Motion(port)
        try:
            motion.attach(client)
            if scenario == 'lost_ack':
                port.drop_command = 'G1 X1'
                motion.relay(b'G1 X1\n')
                motion.detach(client)
            elif scenario == 'reset':
                port.reply(b'Smoothie command shell\r\n')
                until(lambda: bool(motion.snapshot()['fault']))
            else:
                motion.action({'action':'halt'})
                assert client.closed and port.halted
            assert motion.snapshot()['fault'] and not motion.snapshot()['web_homed']
            rejected(lambda: motion.attach(Client()))
        finally:
            motion.close()


def connected_jog_checks():
    class FragmentedPeer(SimulatedMotion):
        @property
        def in_waiting(self):
            return min(1, super().in_waiting)
    port = FragmentedPeer()
    # Nonzero offsets distinguish OpenPnP's work coordinates from machine bounds.
    port.position.update(X=100, Y=50, Z=2, A=40, B=-20)
    port.offsets.update(X=-70, Y=10, Z=-1, A=-40, B=20)
    motion = Motion(port, timeout=0.1)
    stock = host.Stock(':memory:')
    feeders = host.Feeders(SimulatedBus(), stock, [1])
    tcp = MotionServer(0, motion)
    web = host.WebServer(0, feeders, demo=True, motion=motion)
    servers = (tcp, web)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for thread in threads:
        thread.start()
    connection = http.client.HTTPConnection(*web.server_address, timeout=3)
    def request(args):
        connection.request('POST', '/api/motion', json.dumps(args), {'Content-Type':'application/json'})
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    confirmed = dict(idle_confirmed=True, homed_confirmed=True)
    try:
        with socket.create_connection(tcp.server_address, timeout=2) as client:
            client.settimeout(2)
            stream = client.makefile('rb')
            until(lambda: motion.snapshot()['owner'] == 'openpnp')
            before = len(port.writes)
            assert request({'action':'jog_connected', 'axis':'X', 'distance':1})[0] == 400
            assert len(port.writes) == before
            # A report-only probe emits work coordinates, no private ok replies.
            assert request(dict(action='report_connected', **confirmed))[0] == 200
            expected = b'C: X:30.0000 Y:60.0000 Z:1.0000 A:0.0000 B:0.0000\r\n'
            assert stream.readline() == expected
            assert motion.snapshot()['position_reports_sent'] == 1
            assert request(dict(action='jog_connected', axis='X', distance=1, **confirmed))[0] == 200
            assert stream.readline() == expected.replace(b'X:30.', b'X:31.')
            assert port.position['X'] == 101
            assert request(dict(action='jog_connected', axis='A', distance=5, **confirmed))[0] == 200
            assert stream.readline() == expected.replace(b'X:30.', b'X:31.').replace(b'A:0.', b'A:5.')
            assert port.position['A'] == 45  # Offset is preserved, not rotated twice.
            assert not motion.snapshot()['fault'] and motion.snapshot()['owner'] == 'openpnp'
            assert motion.snapshot()['position_reports_sent'] == 3
            assert request(dict(action='jog_connected', axis='X', distance=0, **confirmed))[0] == 400
            # No hidden manual acknowledgement remains ahead of this real reply.
            client.sendall(b'M114\n')
            assert stream.readline() == b'ok ' + expected.replace(b'X:30.', b'X:31.').replace(b'A:0.', b'A:5.')
            until(lambda: motion.snapshot()['pending'] == 0)
            # An incomplete OpenPnP command refuses the operation before serial writes.
            client.sendall(b'G90')
            until(lambda: bool(motion.tx_fragment))
            before = len(port.writes)
            assert request(dict(action='report_connected', **confirmed))[0] == 409
            assert len(port.writes) == before
            client.sendall(b'\n')
            assert stream.readline() == b'ok\r\n'
            until(lambda: motion.snapshot()['pending'] == 0)
            # Commands arriving during a web move are never queued for later use.
            port.defer_completion = True
            failures = []
            worker = threading.Thread(target=lambda: run_action(motion, dict(action='jog_connected', axis='X', distance=1, **confirmed), failures))
            worker.start()
            until(lambda: port.target is not None and port.commands[-1] == 'M400')
            client.sendall(b'G1 X123 F600\n')
            worker.join(2)
            assert not worker.is_alive() and failures and motion.snapshot()['fault']
            assert 'G1 X123 F600' not in port.commands
            assert stream.read() == b''  # No leaked ok/partial position upon failure.
            stream.close()
    finally:
        connection.close()
        for server in servers:
            server.shutdown()
            server.server_close()
        motion.close()
        stock.close()
        for thread in threads:
            thread.join()


if __name__ == '__main__':
    manual_checks()
    network_checks()
    relay_fault_checks()
    connected_jog_checks()
    print('Motion checks passed: byte-exact TCP relay, HTTP ownership, MCS jog bounds, completion, outputs, halt and uncertain failures')
