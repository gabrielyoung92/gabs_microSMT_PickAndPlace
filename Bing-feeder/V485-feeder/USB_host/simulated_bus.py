"""Small protocol simulator for host development. No hardware is opened.

This checks PC behaviour, not STM32 timing or physical feeder operation.
"""
from collections import deque
import time
from rs485_upload import decode_packet, packet


class SimulatedBus:
    def __init__(self):
        self.nodes = {n: dict(uid=(n, 0x485, n * 17), token=(0, 0), counter=0,
                              default=4, options=(False,False,False), width=8, fault=0, armed=False, motion=None, target=0)
                      for n in (0, 1, 2)}
        self.nodes[0]["armed"] = True  # Demo of a feeder with menu 01 selected.
        self.rx = deque()
        self.frames = []
        self.closed = False
        self.echo = False
        self.lose_accept = False
        self.drop_status = 0
        self.stall = self.unknown = self.fail_diag = False
        self.feed_delay = 0.03
        self.feeds = 0

    def write(self, raw):
        if self.closed:
            raise OSError("Simulated adapter closed")
        address = int(raw[1:3])
        body = decode_packet(raw, address)
        if body is None:
            return len(raw)
        self.frames.append((address, body))
        if self.echo:
            self.rx.append(raw)
        node = self.nodes.get(address)
        if node is None:
            return len(raw)
        values = body.split()

        def reply(text):
            self.rx.append(packet(address, text))

        if values[0] == "IDENT":
            reply("IDENT " + values[1] + " " + " ".join(f"{n:08X}" for n in (*node["uid"], int(node["armed"]))))
        elif values[0] in ("DIAG", "MONITOR"):
            if self.fail_diag:
                return len(raw)
            if values[0] == "MONITOR" and node["token"] == (0, 0):
                node["token"] = tuple(int(n, 16) for n in values[2:4])
            state = 3 if node["fault"] else 2 if node.get("manual_running") else 0
            flags = node["default"] | (node["fault"] << 8) | (state << 16) | ((6 if node.get("test_active") else int(node["armed"]) * 2) << 20) | (1 << 26) | (1 << 29)
            if address:
                flags |= 1 << 27
            flags |= ((8,12,16,24).index(node["width"]) << 30) | ((node["width"] != 8) << 28)
            reply("DIAG " + values[1] + " " + " ".join(f"{n:08X}" for n in (*node["token"], node["counter"], flags)))
        elif values[0] == "SETID":
            uid = tuple(int(n, 16) for n in values[2:5])
            new_id = int(values[5], 16)
            if uid == node["uid"] and node["armed"] and 1 <= new_id <= 99:
                self.nodes[new_id] = self.nodes.pop(address)
                node["armed"] = False
                reply(f"ID {values[1]} {new_id:08X}")
            else:
                reply("ERROR NOTARMED")
        elif values[0] == 'CONFIG':
            reply('CONFIG '+values[1]+''.join(f' {int(v):08X}' for v in node['options']))
        elif values[0] == 'TYPE':
            reply(f"TYPE {values[1]} {node['width']:08X} {node['default']:08X} {(2000 if node['width']==8 else 4000):08X}")
        elif values[0] in ('SETCONFIG','SETCOUNT'):
            if tuple(int(n,16) for n in values[2:5]) != node['uid']:
                reply('ERROR UID')
            elif values[0] == 'SETCONFIG':
                node['options'] = tuple(int(n,16) for n in values[5:8])
                reply('CONFIGSET '+values[1]+''.join(f' {v:08X}' for v in node['options']))
            else:
                node['default'] = int(values[5],16)
                reply(f"COUNTSET {values[1]} {node['default']:08X}")
        elif values[0] in ('TESTREAD','TEST'):
            if node.get('old_firmware'):return len(raw)
            if values[0]=='TEST':
                if tuple(int(n,16) for n in values[2:5])!=node['uid']:return len(raw)
                if node.get('manual_running') or node['armed']:
                    reply('BUSY '+values[1]);return len(raw)
                node['test_active']=bool(int(values[5],16))
            flags=int(node.get('test_active',False)) | (int(node.get('contact_closed',False))<<1)
            request=node.get('contact_closed',False)^bool(node['options'][2])
            flags|=int(request)<<2
            reply(f"TEST {values[1]} {flags:08X} {node.get('switch_changes',0):08X} 00001000 {node['counter']:08X}")
        elif values[0] == "FEED":
            self.feeds += 1
            tokens = " ".join(values[1:3])
            if address == 0 or node["fault"]:
                reply("FAULT " + tokens)
            elif node["armed"] or node.get("test_active"):
                reply("BUSY " + tokens)
            else:
                node["motion"] = (tokens, time.monotonic())
                node["target"] = int(values[3], 16) or node["default"]
                if not self.lose_accept:
                    reply("ACCEPT " + tokens)
        elif values[0] == "STATUS":
            if self.drop_status:
                self.drop_status -= 1
                return len(raw)
            tokens = " ".join(values[1:3])
            if self.unknown or node["motion"] is None or node["motion"][0] != tokens:
                reply("UNKNOWN " + tokens)
            elif node["fault"]:
                reply("FAULT " + tokens)
            elif self.stall or time.monotonic() - node["motion"][1] < self.feed_delay:
                reply("RUNNING " + tokens)
            else:
                node["counter"] = (node["counter"] + node["target"]) & 0xFFFFFFFF
                node["target"] = 0
                reply("DONE " + tokens)
        elif values[0] == "INFO":
            reply(f"APP 00000003 {node.get('image_size',1024):08X} {node.get('image_crc',0x12345678):08X}")
        elif values[0] in ("HELLO", "BOOT", "BEGIN", "DATA", "END"):
            reply("ERROR DEMO_NO_FLASH")
        return len(raw)

    def flush(self):
        pass

    def reset_input_buffer(self):
        self.rx.clear()

    def read_until(self, *args):
        if self.closed:
            raise OSError("Simulated adapter closed")
        if self.rx:
            return self.rx.popleft()
        time.sleep(0.001)
        return b""

    def close(self):
        self.closed = True
