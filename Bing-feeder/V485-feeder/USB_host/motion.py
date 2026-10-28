"""Smoothieware USB owner, transparent OpenPnP TCP relay and manual controls.

No serial reopen, command replay or background polling injection. Explicit
connected web jogs isolate private replies and publish one work-position line.
Original machine/firmware: MicroSMT; local integration by Gab with ChatGPT.
"""
from collections import deque
import math
import re
import socket
import socketserver
import threading
import time

AXES = 'XYZAB'
LIMITS = {'X': (0, 385), 'Y': (0, 470), 'Z': (-30, 30)}
OUTPUTS = {'pump': (808, 809), 'n1_valve': (800, 801), 'n2_valve': (802, 803),
           'top_light': (806, 807), 'bottom_light': (804, 805)}
ERROR = re.compile(r'^(?:error\b|alarm\b|!!|halt(?:ed)?\b)|\bEntering Alarm/Halt\b', re.I)
POSITION = re.compile(r'\b([XYZAB]):\s*(-?(?:\d+(?:\.\d*)?|\.\d+))')


class MotionError(Exception):
    pass


def number(value, low, high, name):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be {low}..{high}')
    return float(value)


class Motion:
    def __init__(self, port, timeout=10):
        self.port, self.timeout = port, timeout
        self.lock = threading.RLock()
        self.operation = threading.Lock()
        self.write_lock = threading.Lock()
        self.tcp_send_lock = threading.Lock()
        self.stopped = threading.Event()
        self.owner = 'available'
        self.client = None
        self.busy = False
        self.fault = ''
        self.homed = False  # Only a completed web home establishes this claim.
        self.position = {}
        self.position_kind = 'unknown'
        self.position_at = None
        self.outputs = {name: None for name in OUTPUTS}
        self.motors = None
        self.endstops = ''
        self.pending = deque()
        self.tx_fragment = b''
        self.tracking_lost = False
        self.rx_partial = 0
        self.position_report = None
        self.position_reports_sent = 0
        self.recent = deque(maxlen=40)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _log(self, direction, text):
        self.recent.append(dict(time=time.time(), direction=direction, text=text[:500]))

    def _fail(self, message):
        with self.lock:
            interrupted = self.client if self.owner == 'connected_manual' else None
            self.fault = str(message)[:500]
            self.homed = False
            self.outputs = {name: None for name in OUTPUTS}
            self.motors = None
            while self.pending:
                item = self.pending.popleft()
                item['error'] = self.fault
                item['done'].set()
        if interrupted is not None:
            try:
                interrupted.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _accepted(self, command):
        for name, codes in OUTPUTS.items():
            for enabled, code in ((True, codes[0]), (False, codes[1])):
                if re.search(rf'\bM{code}\b', command):
                    self.outputs[name] = enabled
        if re.search(r'\bM17\b', command):
            self.motors = True
        if re.search(r'\bM(?:18|84)\b', command):
            self.motors = False
            self.homed = False

    def _line(self, text):
        with self.lock:
            self._log('rx', text)
            values = {axis: float(value) for axis, value in POSITION.findall(text)}
            if all(axis in values and math.isfinite(values[axis]) for axis in AXES):
                self.position = values
                self.position_kind = 'machine' if 'MCS:' in text else 'work / commanded'
                self.position_at = time.time()
            if 'Smoothie command shell' in text:
                self._fail('Controller restarted; restart the bridge after inspecting the machine')
            if ERROR.search(text):
                self._fail(text)
            if self.pending:
                item = self.pending[0]
                item['lines'].append(text)
                if re.match(r'^ok\b', text, re.I):
                    self.pending.popleft()
                    if not self.fault:
                        self._accepted(item['command'])
                    item['done'].set()

    def _read(self):
        fragment = b''
        try:
            while not self.stopped.is_set():
                data = self.port.read(max(1, min(512, self.port.in_waiting)))
                if not data:
                    continue
                with self.lock:
                    client = self.client
                    private = self.owner == 'connected_manual'
                # Ordinary relay replies remain byte-exact. Explicit connected
                # web operations consume their own replies, including every ok.
                if client is not None and not private:
                    try:
                        with self.tcp_send_lock:
                            client.sendall(data)
                    except OSError:
                        self._fail('OpenPnP reply connection lost; completion is uncertain')
                        try:
                            client.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                fragment += data
                with self.lock:
                    self.rx_partial = len(fragment.rsplit(b'\n', 1)[-1])
                while b'\n' in fragment:
                    raw, fragment = fragment.split(b'\n', 1)
                    self._line(raw.rstrip(b'\r').decode('ascii', errors='replace'))
                if len(fragment) > 8192:
                    self._fail('Controller reply exceeded the observation limit')
                    fragment = b''
        except OSError as error:
            if not self.stopped.is_set():
                self._fail(f'Motion serial connection lost: {error}')
                with self.lock:
                    client = self.client
                if client:
                    try:
                        client.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

    def attach(self, client):
        with self.lock:
            if self.owner != 'available' or self.fault or self.busy or self.pending:
                raise MotionError('Motion controller unavailable: manual control, another client or unresolved fault')
            self.owner, self.client = 'openpnp', client
            self.homed = False
            self.tx_fragment = b''
            self.tracking_lost = False

    def detach(self, client):
        with self.lock:
            if self.client is not client:
                return
            self.client = None
            self.owner = 'available'
            if self.pending or self.tx_fragment or self.tracking_lost:
                self._fail('OpenPnP disconnected with unresolved commands; inspect machine and restart bridge')
            self.tx_fragment = b''

    def relay(self, data):
        with self.write_lock, self.lock:
            if self.owner != 'openpnp' or self.fault:
                raise MotionError(self.fault or 'OpenPnP sent commands during a connected web jog; request was not queued')
            # Observation never rewrites the bytes sent to the controller.
            self.tx_fragment += data.replace(b'\r\n', b'\n')
            while b'\n' in self.tx_fragment:
                raw, self.tx_fragment = self.tx_fragment.split(b'\n', 1)
                text = raw.rstrip(b'\r').decode('ascii', errors='replace')
                self._log('tx', text)
                if not text or text[0] in 'GMTNS;(':
                    self.pending.append(dict(command=text, done=threading.Event(), lines=[], error=''))
                else:
                    # Console commands may have no `ok`. Pass through, but do
                    # not claim that a subsequent disconnect is synchronised.
                    self.tracking_lost = True
            if len(self.tx_fragment) > 4096 or len(self.pending) > 1024:
                self._fail('OpenPnP observation backlog exceeded; no command will be replayed')
                raise MotionError(self.fault)
            try:
                if self.port.write(data) != len(data):
                    raise OSError('Partial serial write')
            except OSError as error:
                self._fail(f'Serial write failed; command outcome uncertain: {error}')
                raise MotionError(self.fault) from error

    def _command(self, command, timeout=None):
        item = dict(command=command, done=threading.Event(), lines=[], error='')
        raw = (command + '\n').encode('ascii')
        with self.write_lock, self.lock:
            if self.fault:
                raise MotionError(self.fault)
            self.pending.append(item)
            self._log('tx', command)
            try:
                if self.port.write(raw) != len(raw):
                    raise OSError('Partial serial write')
            except OSError as error:
                self._fail(f'Serial write failed; command outcome uncertain: {error}')
        if not item['done'].wait(self.timeout if timeout is None else timeout):
            self._fail(f'{command.split()[0]} timed out; outcome uncertain, no automatic retry')
            raise MotionError(self.fault)
        if item['error'] or self.fault:
            raise MotionError(item['error'] or self.fault)
        reply = '\n'.join(item['lines'])
        if re.search(r'^ok\s*-', reply, re.M | re.I):
            self._fail(f'Controller rejected command: {reply}')
            raise MotionError(self.fault)
        return reply

    def _position(self):
        reply = self._command('M114.2')
        values = dict(POSITION.findall(reply))
        if 'MCS:' not in reply or not all(axis in values and math.isfinite(float(values[axis])) for axis in AXES):
            self._fail('Expected five-axis M114.2 machine position; verify controller firmware')
            raise MotionError(self.fault)

    def _publish_position(self, client):
        # OpenPnP uses its work coordinates, including G92 and rotary offsets.
        # MCS values would move its coordinate origin. Strip only the private
        # acknowledgement; a stray ok could release its async writer early.
        reply = self._command('M114')
        for line in reply.splitlines():
            values = dict(POSITION.findall(line))
            if all(a in values and math.isfinite(float(values[a])) for a in AXES):
                report = re.sub(r'^ok\s+', '', line, flags=re.I)
                if 'MCS:' in report or re.match(r'^ok\b', report, re.I):
                    break
                with self.lock:
                    if self.fault or self.client is not client:
                        raise MotionError(self.fault or 'OpenPnP disconnected before position publication')
                with self.tcp_send_lock:
                    client.sendall((report + '\r\n').encode('ascii'))
                with self.lock:
                    self.position_report = dict(text=report, sent_at=time.time())
                    self.position_reports_sent += 1
                    self._log('to_openpnp', report)
                return
        self._fail('Expected a five-axis work-coordinate M114 report for OpenPnP')
        raise MotionError(self.fault)

    def _connected_action(self, args):
        if args.get('idle_confirmed') is not True or args.get('homed_confirmed') is not True:
            raise ValueError('Confirm OpenPnP is enabled, homed and idle, with no running job')
        if not self.operation.acquire(blocking=False):
            raise MotionError('A manual operation is already running; request was not queued')
        reserved = False
        try:
            with self.write_lock, self.lock:
                if self.fault or self.owner != 'openpnp' or self.client is None:
                    raise MotionError(self.fault or 'A connected idle OpenPnP motion driver is required')
                if self.pending or self.tx_fragment or self.rx_partial or self.tracking_lost:
                    raise MotionError('OpenPnP has unresolved or partial traffic; wait until idle')
                client = self.client
                self.owner, self.busy, self.homed = 'connected_manual', True, True
                reserved = True
            self._command('M400', 120)
            if args['action'] == 'jog_connected':
                self._jog(args)
            self._publish_position(client)
        except (OSError, MotionError) as error:
            if reserved:
                self._fail(f'Connected web operation failed: {error}')
            raise MotionError(str(error)) from error
        finally:
            with self.lock:
                if reserved:
                    self.owner = 'openpnp' if self.client is not None else 'available'
                    self.busy = self.homed = False
            self.operation.release()

    def _jog(self, args):
        axis = args.get('axis')
        if not isinstance(axis, str) or len(axis) != 1 or axis not in AXES:
            raise ValueError('Axis must be X, Y, Z, A or B')
        delta = number(args.get('distance'), -90 if axis in 'AB' else -10,
                       90 if axis in 'AB' else 10, 'Jog distance')
        if delta == 0:
            raise ValueError('Jog distance must be nonzero')
        speed = number(args.get('speed', 10), 0.1, 60 if axis in 'AB' else 10 if axis == 'Z' else 100, 'Speed')
        if not self.homed:
            raise MotionError('Home through the web controls before jogging in this manual session')
        self._position()
        target = self.position[axis] + delta
        if axis in LIMITS and not LIMITS[axis][0] <= target <= LIMITS[axis][1]:
            raise ValueError(f'{axis} target {target:g} is outside {LIMITS[axis]} mm')
        self._command('G21')
        self._command('G90')
        if axis in 'AB':
            # This firmware applies G92 offsets to ABC even under G53.
            # Use its reported work angle for absolute rotary jogs.
            reply = self._command('M114')
            angles = dict(POSITION.findall(reply))
            if axis not in angles or not math.isfinite(float(angles[axis])):
                self._fail('Missing rotary work position in M114 reply')
                raise MotionError(self.fault)
            target = float(angles[axis]) + delta
            self._command(f'G1 {axis}{target:.4f} F{speed * 60:.2f}')
        else:
            self._command(f'G53 G1 {axis}{target:.4f} F{speed * 60:.2f}')
        self._command('M400', 120)
        self._position()

    def action(self, args):
        if not isinstance(args, dict):
            raise ValueError('Expected a JSON object')
        action = args.get('action')
        if action in {'jog_connected', 'report_connected'}:
            return self._connected_action(args)
        if action == 'halt':
            # Verified USBSerial Ctrl-X handler acts out of band and flushes
            # queued USB input. This is software halt, not a physical E-stop.
            with self.write_lock:
                try:
                    if self.port.write(b'\x18') != 1:
                        raise OSError('Partial halt write')
                    self._fail('Software halt requested; inspect machine, reset controller and restart bridge')
                except OSError as error:
                    self._fail(f'Could not send software halt: {error}')
                    raise MotionError(self.fault) from error
            with self.lock:
                client = self.client
            if client:
                try:
                    client.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            return
        if action not in {'claim', 'release', 'read', 'home', 'jog', 'enable', 'disable', 'output', 'all_off'}:
            raise ValueError('Unknown motion action')
        if not self.operation.acquire(blocking=False):
            raise MotionError('A manual operation is already running; request was not queued')
        try:
            with self.lock:
                if self.fault:
                    raise MotionError(self.fault)
                if action == 'claim':
                    if self.owner != 'available':
                        raise MotionError('Disconnect OpenPnP before taking manual control')
                    self.owner = 'manual'
                    self.homed = False
                elif self.owner != 'manual':
                    raise MotionError('Take manual control first')
                self.busy = True
            # M400 establishes physical completion; an `ok` for G1 does not.
            if action in {'claim', 'release', 'read', 'jog', 'disable', 'all_off'}:
                self._command('M400', 120)
            if action == 'claim':
                self._command('G21')
                self._command('G90')
                self._position()
            elif action == 'release':
                with self.lock:
                    self.owner = 'available'
                    self.homed = False
            elif action == 'read':
                self._position()
                reply = self._command('M119')
                with self.lock:
                    self.endstops = reply
            elif action == 'home':
                if args.get('heads_ready') is not True:
                    raise ValueError('Confirm heads level or N2 below N1 before the central Z homing search')
                with self.lock:
                    self.homed = False
                for command in ('G21', 'G90', 'G28', 'M400', 'G92 A0 B0'):
                    self._command(command, 120)
                self._position()
                with self.lock:
                    self.homed = True
            elif action == 'jog':
                self._jog(args)
            elif action == 'enable':
                self._command('M17')
            elif action in {'disable', 'all_off'}:
                for name in OUTPUTS:
                    self._command(f'M{OUTPUTS[name][1]}')
                if action == 'disable':
                    self._command('M84')
            elif action == 'output':
                name, enabled = args.get('name'), args.get('enabled')
                if not isinstance(name, str) or name not in OUTPUTS or type(enabled) is not bool:
                    raise ValueError('Choose a known output and true/false state')
                self._command(f'M{OUTPUTS[name][0 if enabled else 1]}')
        finally:
            with self.lock:
                self.busy = False
            self.operation.release()

    def snapshot(self):
        with self.lock:
            return dict(configured=True, owner=self.owner, busy=self.busy, fault=self.fault,
                        web_homed=self.homed, position=dict(self.position), position_kind=self.position_kind,
                        position_at=self.position_at, outputs=dict(self.outputs), motors=self.motors,
                        endstops=self.endstops, pending=len(self.pending), recent=list(self.recent), limits=LIMITS,
                        openpnp_connected=self.client is not None,
                        position_report=dict(self.position_report) if self.position_report else None,
                        position_reports_sent=self.position_reports_sent)

    def close(self):
        self.stopped.set()
        with self.lock:
            client = self.client
        if client:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.port.close()
        self.reader.join(timeout=3)


class MotionServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, port, motion):
        self.motion = motion
        super().__init__(('127.0.0.1', port), MotionHandler)


class MotionHandler(socketserver.BaseRequestHandler):
    def handle(self):
        motion = self.server.motion
        self.request.settimeout(1)
        try:
            motion.attach(self.request)
        except MotionError as error:
            self.request.sendall(('error: ' + str(error) + '\n').encode())
            return
        try:
            while not motion.stopped.is_set():
                try:
                    data = self.request.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                motion.relay(data)
        except (OSError, MotionError) as error:
            motion._fail(str(error))
        finally:
            motion.detach(self.request)
