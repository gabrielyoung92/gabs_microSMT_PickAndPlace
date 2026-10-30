"""Small protocol simulator for host development. No hardware is opened.

This checks PC behaviour, not STM32 timing or physical feeder operation.
"""
from collections import deque
import time
from rs485_upload import decode_packet, packet


class SimulatedBus:
    def __init__(self):
        self.nodes = {n: dict(uid=(n, 0x485, n * 17), token=(0, 0), counter=0,
                              default=4, options=(False,False,False), width=8, fault=0, armed=False, motion=None, target=0,
                              stock_supported=True, remaining=None, advances=0, stock_sequence=0)
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

    def completed(self,address,count=1,events=None):
        node=self.nodes[address]
        node['counter']=(node['counter']+(node['default']*count if events is None else events))&0xFFFFFFFF
        node['advances']=min(0xFFFFFFFF,node['advances']+count)
        if node['remaining'] is not None:node['remaining']=max(0,node['remaining']-count)
        node['stock_sequence']=(node['stock_sequence']+count)&0xFFFFFFFF

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

        if values[0] == 'HEALTH':
            if not node.get('old_firmware'):reply(f"HEALTH {values[1]} {node.get('reset_flags',1<<27):08X} 00001000")
            return len(raw)
        if values[0] == 'FAULTINFO':
            if not node.get('old_firmware'):reply(f"FAULTINFO {values[1]} {node['fault']:08X} {node.get('fault_target',0):08X} {node.get('fault_received',0):08X} {node.get('fault_duration',0):08X}")
            return len(raw)
        if values[0] == 'LOCATE':
            reply(('BUSY' if node['fault'] or node['target'] or node.get('load_active') or node.get('test_active') or node['armed'] else 'LOCATING')+' '+values[1])
            return len(raw)
        if values[0] == 'LOAD':
            if node.get('old_firmware'):return len(raw)
            if tuple(int(n,16) for n in values[2:5])!=node['uid']:return len(raw)
            action=int(values[5],16)
            if node['armed'] or node.get('test_active') or (node['target'] and action!=3) or (node['fault'] and action not in (0,3)) or (action>=2 and not node.get('load_active')):
                reply('BUSY '+values[1]);return len(raw)
            node['load_active']=action!=0;node['load_peel']=action==2 and (node.get('contact_closed',False)^bool(node['options'][2]))
            if action==3:node['target']=0
            reply(f"LOAD {values[1]} {int(node['load_active']):08X} {int(node['load_peel']):08X}")
            return len(raw)
        if values[0] in ('STOCKREAD','SETSTOCK'):
            if not node['stock_supported']:return len(raw)
            if values[0]=='SETSTOCK':
                if tuple(int(n,16) for n in values[2:5])!=node['uid']:return len(raw)
                if node['armed'] or node.get('test_active') or node.get('manual_running') or node['target']:
                    reply('BUSY '+values[1]);return len(raw)
                quantity=int(values[5],16)
                if quantity>65534:reply('ERROR QUANTITY');return len(raw)
                node.update(remaining=quantity,advances=0,stock_sequence=(node['stock_sequence']+1)&0xFFFFFFFF)
                if node.get('lose_stock_ack'):return len(raw)
            quantity=65535 if node['remaining'] is None else node['remaining']
            reply(f"STOCK {values[1]} {quantity:08X} {node['advances']:08X} {node['stock_sequence']:08X}")
        elif values[0] == "IDENT":
            reply("IDENT " + values[1] + " " + " ".join(f"{n:08X}" for n in (*node["uid"], int(node["armed"]))))
        elif values[0] in ("DIAG", "MONITOR"):
            if self.fail_diag:
                return len(raw)
            if values[0] == "MONITOR" and node["token"] == (0, 0):
                node["token"] = tuple(int(n, 16) for n in values[2:4])
            state = 3 if node["fault"] else 2 if node.get("manual_running") else 0
            flags = node["default"] | (node["fault"] << 8) | (state << 16) | ((7 if node.get("load_active") else 6 if node.get("test_active") else int(node["armed"]) * 2) << 20) | (1 << 26) | ((node['width'] in (8,12,16,24)) << 29)
            if address:
                flags |= 1 << 27
            flags |= (((8,12,16,24).index(node['width']) if node['width'] in (8,12,16,24) else 0) << 30) | ((node["width"] != 8) << 28)
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
        elif values[0] in ('SETCONFIG','SETCOUNT','SETTYPE'):
            if tuple(int(n,16) for n in values[2:5]) != node['uid']:
                reply('ERROR UID')
            elif values[0] == 'SETCONFIG':
                node['options'] = tuple(int(n,16) for n in values[5:8])
                node['invalid_settings']=False
                reply('CONFIGSET '+values[1]+''.join(f' {v:08X}' for v in node['options']))
            elif values[0]=='SETTYPE':
                node['width']=int(values[5],16)
                reply(f"TYPESET {values[1]} {node['width']:08X}")
            else:
                node['default'] = int(values[5],16)
                reply(f"COUNTSET {values[1]} {node['default']:08X}")
        elif values[0] == 'CLEAR':
            if node.get('no_clear'):return len(raw)
            if tuple(int(n,16) for n in values[2:5])!=node['uid']:return len(raw)
            if node.get('manual_running') or node['motion'] or node['armed']:
                reply('BUSY '+values[1])
            elif node.get('invalid_settings'):
                reply('ERROR SETTINGS '+values[1])
            else:
                node['fault']=0
                reply('CLEARED '+values[1])
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
        elif values[0] in ("FEED","JOG"):
            node["jog"]=values[0]=="JOG"
            self.feeds += 1
            tokens = " ".join(values[1:3])
            if address == 0 or node["fault"]:
                reply("FAULT " + tokens)
            elif node["armed"] or node.get("test_active") or (node.get("load_active") and values[0]=="FEED"):
                reply("BUSY " + tokens)
            else:
                node["motion"] = (tokens, time.monotonic())
                node["target"] = node["default"] if values[0]=="JOG" else int(values[3], 16) or node["default"]
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
                if node["target"]:
                    if node.get('jog'):node['counter']=(node['counter']+node['target'])&0xFFFFFFFF
                    else:self.completed(address,events=node['target'])
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

    @property
    def in_waiting(self):
        return sum(map(len, self.rx))

    def read_until(self, *args):
        if self.closed:
            raise OSError("Simulated adapter closed")
        if self.rx:
            return self.rx.popleft()
        time.sleep(0.001)
        return b""

    def close(self):
        self.closed = True
