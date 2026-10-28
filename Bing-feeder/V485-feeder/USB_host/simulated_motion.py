"""Offline Smoothieware peer for bridge/UI checks; never opens hardware."""
import re
import threading
from motion import AXES


class SimulatedMotion:
    def __init__(self):
        self.condition = threading.Condition()
        self.rx = bytearray()
        self.fragment = b''
        self.position = dict.fromkeys(AXES, 0.0)
        self.offsets = dict.fromkeys(AXES, 0.0)
        self.writes = []
        self.commands = []
        self.closed = self.halted = False
        self.drop_command = None
        self.error_command = None
        self.defer_completion = False
        self.target = None

    @property
    def in_waiting(self):
        with self.condition:
            return len(self.rx)

    def reply(self, data):
        with self.condition:
            self.rx.extend(data)
            self.condition.notify_all()

    def write(self, raw):
        if self.closed:
            raise OSError('Simulated controller disconnected')
        self.writes.append(raw)
        if b'\x18' in raw:
            self.halted = True
            self.fragment = b''
            self.reply(b'HALTED, M999 or $X to exit HALT state\r\n')
            return len(raw)
        self.fragment += raw.replace(b'\r\n', b'\n')
        while b'\n' in self.fragment:
            line, self.fragment = self.fragment.split(b'\n', 1)
            command = line.rstrip(b'\r').decode('ascii')
            self.commands.append(command)
            if self.drop_command == command:
                continue
            if self.error_command == command:
                self.reply(b'error: simulated controller fault\r\n')
                continue
            if self.halted:
                self.reply(b'!!\r\n')
                continue
            if command == 'G28':
                self.position.update(X=0.0, Y=0.0, Z=0.0)
            if command.startswith('G92 '):
                for axis, value in re.findall(r'([XYZAB])(-?[0-9.]+)', command):
                    self.offsets[axis] = float(value) - self.position[axis]
            if command.startswith(('G53 G1 ', 'G1 ')):
                target = dict(self.position)
                for axis, value in re.findall(r'([XYZAB])(-?[0-9.]+)', command):
                    target[axis] = float(value) - (self.offsets[axis] if axis in 'AB' or not command.startswith('G53') else 0)
                if self.defer_completion:
                    self.target = target
                else:
                    self.position = target
            if command == 'M400' and self.target is not None:
                continue  # Test releases physical completion explicitly.
            if command.startswith('M114'):
                prefix = 'MCS:' if command == 'M114.2' else 'C:'
                position = self.position if command == 'M114.2' else {a:self.position[a]+self.offsets[a] for a in AXES}
                self.reply(('ok ' + prefix + ' ' + ' '.join(f'{a}:{position[a]:.4f}' for a in AXES) + '\r\n').encode())
            elif command == 'M119':
                self.reply(b'X_min:0 Y_min:0 Z_min:1\r\nok\r\n')
            else:
                self.reply(b'ok\r\n')
        return len(raw)

    def complete_move(self):
        assert self.target is not None
        self.position, self.target = self.target, None
        self.reply(b'ok\r\n')

    def read(self, size):
        with self.condition:
            if not self.rx and not self.closed:
                self.condition.wait(0.05)
            if self.closed:
                raise OSError('Simulated controller disconnected')
            data = bytes(self.rx[:size])
            del self.rx[:size]
            return data

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
