#!/usr/bin/env python3
"""MicroSMT powered-feeder dashboard and local OpenPnP feeder TCP service.

One owner of a direct auto-direction USB-RS485 adapter, at 115200 8N1.
Stock is informational. Hardware control/deadlines remain on each STM32.
Original MicroSMT authors retain credit; local changes by Gab with ChatGPT.
"""
import argparse
from collections import deque
import json
import logging
import os
from pathlib import Path
import re
import secrets
import socket
import socketserver
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError

# Reuse the maintained packet, update and ID tools rather than fork their wire
# protocol. Run this folder with its sibling CODE_feeder folder present.
TOOLS = Path(__file__).resolve().parents[1] / "CODE_feeder" / "tools"
sys.path.insert(0, str(TOOLS))
from rs485_upload import APP_MAX, Link, UpdateError, decode_packet, fields, inspect_image, packet, upload
from assign_id import assign
from configure_unit import read_options, save_options, set_count, events_for_pitch
from bundle_firmware import BUNDLE, read_bundle
from dashboard_tools import job_stock

VERSION = "0.1.4"
BAUD = 115200
OPENPNP_URL = 'http://127.0.0.1:5004'


FAULTS = {0: "none", 1: "index_timeout", 2: "peel_timeout", 3: "settings_error", 4: "stopped"}
FEED_STATES = ("idle", "reserved", "running", "fault")
MODES = ("normal", "menu", "assign_id", "edit_id", "edit_count", "edit_type", "test", "load")
log = logging.getLogger("v485")


class ServiceError(Exception):
    pass


def openpnp_request(path, body=None, timeout=0.5):
    request = Request(OPENPNP_URL + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={'Content-Type': 'application/json'})
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            detail = json.load(error).get('error', 'OpenPnP request failed')
        except (ValueError, OSError):
            detail = 'OpenPnP request failed'
        raise ServiceError(detail) from error
    except (URLError, OSError) as error:
        raise ServiceError('OpenPnP companion unavailable; open OpenPnP and run OpenPnP-Web.py to sync feeder parts.') from error


def integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be {minimum}..{maximum}")
    return value


def parse_ids(text):
    if not isinstance(text, str):
        raise ValueError("Polling addresses must be text")
    result = set()
    for item in text.split(","):
        limits = item.strip().split("-")
        if len(limits) not in (1, 2) or not all(n.isdecimal() for n in limits):
            raise ValueError("IDs must look like 0,1-24 or 1,7,12")
        low, high = int(limits[0]), int(limits[-1])
        if not 0 <= low <= high <= 99:
            raise ValueError("Polling addresses must be 0..99; advances require 1..99")
        result.update(range(low, high + 1))
    return sorted(result)


def state_fields(flags):
    state, mode = (flags >> 16) & 15, (flags >> 20) & 15
    fault = (flags >> 8) & 255
    return dict(default_count=flags & 255, fault_code=fault,
                fault=FAULTS.get(fault, f"unknown_{fault}"),
                state=FEED_STATES[state] if state < len(FEED_STATES) else "unknown",
                mode=MODES[mode] if mode < len(MODES) else "unknown",
                peel_requested=bool(flags & (1 << 24)), switch_closed=bool(flags & (1 << 24)), peel_running=bool(flags & (1 << 25)),
                ready=bool(flags & (1 << 26)), assigned=bool(flags & (1 << 27)),
                configured=bool(flags & (1 << 29)),
                nominal_step_um=(4000 if flags & (1 << 28) else 2000) if flags & (1 << 29) else 0,
                variant=f"{(8, 12, 16, 24)[(flags >> 30) & 3]}mm" if flags & (1 << 29) else "unconfigured")


class Stock:
    """PC inventory keyed by MCU UID, independent of a feeder's editable ID."""
    def __init__(self, path):
        self.lock = threading.RLock()
        self.persistent = str(path) != ":memory:"
        self.path=Path(path) if self.persistent else None
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS feeders (
            uid TEXT PRIMARY KEY, address INTEGER UNIQUE, token TEXT, counter INTEGER,
            flags INTEGER, seen REAL, error TEXT NOT NULL DEFAULT '',
            label TEXT NOT NULL DEFAULT '', loaded INTEGER, pitch INTEGER NOT NULL DEFAULT 1,
            used_pulses INTEGER NOT NULL DEFAULT 0, low INTEGER NOT NULL DEFAULT 50,
            uncertain INTEGER NOT NULL DEFAULT 1)""")
        self.db.execute("CREATE TABLE IF NOT EXISTS device_details (uid TEXT PRIMARY KEY, firmware TEXT, configuration TEXT, part_assignment TEXT, stock TEXT)")
        if 'part_assignment' not in {row[1] for row in self.db.execute('PRAGMA table_info(device_details)')}:
            self.db.execute('ALTER TABLE device_details ADD COLUMN part_assignment TEXT')
        if 'stock' not in {row[1] for row in self.db.execute('PRAGMA table_info(device_details)')}:
            self.db.execute('ALTER TABLE device_details ADD COLUMN stock TEXT')
        self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        self.db.commit()

    def get_setting(self,key,default=None):
        with self.lock:
            row=self.db.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
            return json.loads(row[0]) if row else default

    def save_setting(self,key,value):
        with self.lock,self.db:self.db.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,json.dumps(value)))

    def save_details(self, uid, field, value):
        if field not in ('firmware', 'configuration', 'part_assignment', 'stock'): raise ValueError('Unknown device metadata')
        with self.lock, self.db:
            self.db.execute(f"INSERT INTO device_details(uid,{field}) VALUES(?,?) ON CONFLICT(uid) DO UPDATE SET {field}=excluded.{field}",
                            (uid,json.dumps(value)))

    def observe(self, address, uid, token, counter, flags):
        if token == "0000000000000000":
            raise ValueError("Unclaimed telemetry token")
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM feeders WHERE uid=?", (uid,)).fetchone()
            # A replacement module at an old ID must not inherit the old reel.
            self.db.execute("UPDATE feeders SET address=NULL WHERE address=? AND uid<>?", (address, uid))
            if row is None:
                self.db.execute("INSERT INTO feeders(uid,address,token,counter,flags,seen,pitch) VALUES(?,?,?,?,?,?,?)",
                                (uid, address, token, counter, flags, time.time(), max(1, flags & 255)))
            else:
                uncertain = row["uncertain"]
                if row["token"] != token:
                    # New MCU boot: its current counter is known, but movement
                    # between our last poll and that reset may have been lost.
                    delta, uncertain = counter, 1
                else:
                    delta = (counter - row["counter"]) & 0xFFFFFFFF
                    if delta >= 0x80000000:
                        delta, uncertain = 0, 1
                self.db.execute("""UPDATE feeders SET address=?,token=?,counter=?,flags=?,seen=?,error='',
                    used_pulses=used_pulses+?,uncertain=? WHERE uid=?""",
                                (address, token, counter, flags, time.time(), delta, uncertain, uid))

        return delta if row is not None and row['token']==token else 0

    def failed(self, address, error):
        with self.lock, self.db:
            self.db.execute("UPDATE feeders SET error=? WHERE address=?", (str(error)[:240], address))

    def load(self, uid, label, quantity, pitch, low):
        if quantity is not None:integer(quantity, 0, 65534, "Loaded quantity")
        integer(pitch, 1, 99, "Pulses per part")
        integer(low, 0, 1_000_000_000, "Low-stock threshold")
        if not isinstance(label, str) or len(label) > 128:
            raise ValueError("Reel label must be at most 128 characters")
        with self.lock, self.db:
            if quantity is None:
                row=self.db.execute('SELECT * FROM feeders WHERE uid=?',(uid,)).fetchone()
                if row['pitch']==pitch:
                    self.db.execute('UPDATE feeders SET label=?,low=? WHERE uid=?',(label,low,uid))
                    return
                # Preserve remaining stock when changing the event/part ratio.
                quantity=None if row['loaded'] is None else max(0,row['loaded']-row['used_pulses']/row['pitch'])
                self.db.execute('UPDATE feeders SET label=?,loaded=?,pitch=?,used_pulses=0,low=? WHERE uid=?',
                                (label,quantity,pitch,low,uid))
                return
            self.db.execute("UPDATE feeders SET label=?,loaded=?,pitch=?,used_pulses=0,low=?,uncertain=0 WHERE uid=?",
                            (label, quantity, pitch, low, uid))

    def rows(self):
        with self.lock:
            rows = [dict(row) for row in self.db.execute("SELECT feeders.*, device_details.firmware AS firmware_info, device_details.configuration, device_details.part_assignment, device_details.stock FROM feeders LEFT JOIN device_details USING(uid) ORDER BY address IS NULL,address,uid")]
        for row in rows:
            for field in ('firmware_info','configuration','part_assignment','stock'): row[field] = json.loads(row[field]) if row[field] else None
            row.update(state_fields(row.pop("flags")))
            row["used"] = row["used_pulses"] / row["pitch"]
            row["remaining"] = None if row["loaded"] is None else max(0, row["loaded"] - row["used"])
            info=row.get('stock') or {}
            row['stock_source']='feeder' if info.get('available') else 'computer'
            row['advances']=info.get('advances')
            if info.get('available'):
                row['remaining']=row['loaded']=info.get('remaining')
                row['used']=info.get('advances',0)
                row['uncertain']=bool(info.get('error'))
            row["low_stock"] = row["remaining"] is not None and row["remaining"] <= row["low"]
            row["age_seconds"] = max(0, time.time() - row["seen"])
        return rows

    def close(self):
        self.db.close()


class Feeders:
    def __init__(self, port, stock, ids, reply_timeout=0.3, feed_timeout=12.0, poll_interval=0.1):
        self.port, self.stock, self.ids = port, stock, stock.get_setting('polling_ids',list(ids))
        # One lock covers whole operations, including FEED/STATUS and updates.
        self.bus = threading.RLock()
        self.control = threading.RLock()
        self.reel_lock = threading.RLock()
        self.maintenance = self.updating = False
        self.reply_timeout, self.feed_timeout, self.poll_interval = reply_timeout, feed_timeout, poll_interval
        self.session, self.sequence = secrets.randbits(32), 0
        self.errors = {}
        self.update_status = None
        self.batch_update = None
        self.background_interval = 1.0
        self.activity_condition = threading.Condition(self.control)
        self.activity_revision = 0
        self.activities = {}
        self.active_feeds = set()
        self.activity_events = deque(maxlen=128)
        self.startup_ids = set()
        self.bootloaders = {}
        self.reboots = {}
        self.stock_caps = {}
        self.diagnostics = {}

    def link(self, address):
        return Link(self.port, address, on_packet=self.startup_packet)

    def startup_packet(self, raw):
        # A hello only schedules a normal check; it never marks a device online.
        if not re.match(rb'B[0-9]{2} ONLINE ', raw):return
        address=int(raw[1:3])
        body=decode_packet(raw,address)
        if body is None:return
        try:fields(body,'ONLINE',3)
        except UpdateError:return
        if address in self.ids:self.startup_ids.add(address)

    def record_activity(self,address,stage,label,source='tcp',hold=3,error=None):
        now=time.time()
        with self.activity_condition:
            old=self.activities.get(address)
            if old and old['stage']==stage and old['source']==source and old['expires']>now+1:
                return
            self.activity_revision+=1
            event=dict(id=self.activity_revision,address=address,stage=stage,label=label,
                       source=source,at=now,expires=now+hold,error=error)
            self.activities[address]=event
            self.activity_events.append(event)
            self.activity_condition.notify_all()

    def activity_snapshot(self):
        with self.control:
            now=time.time()
            return dict(server_time=now,activities=[dict(v) for v in self.activities.values() if v['expires']>now])

    def read_firmware(self, address, uid=None):
        """Read image identity; preserve it with this hardware UID across restarts."""
        integer(address, 0, 99, "Address")
        with self.bus:
            uid = uid or self.observe(address)
            try:
                variant, size, checksum = fields(self.link(address).request(
                    "INFO", {"APP"}, timeout=self.reply_timeout, attempts=1), "APP", 3)
                previous=next((r['firmware_info'] or {} for r in self.stock.rows() if r['uid']==uid),{})
                info = dict(variant=variant, size=size, crc32=f"{checksum:08X}", read_at=time.time(), checked_at=time.time())
                if previous.get('crc32')==info['crc32'] and previous.get('size')==size and previous.get('version'):
                    info.update(version=previous['version'],version_source=previous.get('version_source'))
                try:
                    available = read_bundle(BUNDLE)[0]
                    if available['bytes'] == size and available['crc32'] == info['crc32']:
                        info.update(version=available['version'], version_source='image CRC32 and size match bundled build')
                except (OSError, ValueError, KeyError, TypeError): pass
            except (OSError, TimeoutError, UpdateError) as error:
                info = dict(next((r["firmware_info"] or {} for r in self.stock.rows() if r["uid"]==uid),{}), error=str(error)[:240], checked_at=time.time())
            info['monitor_token'] = next((r['token'] for r in self.stock.rows() if r['uid']==uid),None)
            self.stock.save_details(uid, 'firmware', info)
            return uid

    def read_details(self, address, uid=None):
        with self.bus:
            uid = self.read_firmware(address,uid)
            nonce = secrets.randbits(32)
            try:
                values = fields(self.link(address).request(f'CONFIG {nonce:08X}', {'CONFIG'},
                                timeout=self.reply_timeout,attempts=1),'CONFIG',4)
                if values[0] != nonce or any(v not in (0,1) for v in values[1:]):
                    raise UpdateError('Invalid configuration reply')
                config = dict(feed_reverse=bool(values[1]),peel_reverse=bool(values[2]),switch_no=bool(values[3]),read_at=time.time())
            except (OSError,TimeoutError,UpdateError) as error:
                config = dict(error=str(error)[:240],read_at=time.time())
            self.stock.save_details(uid,'configuration',config)
            self.read_stock(address,uid)

    def read_diagnostics(self,address,uid):
        try:
            nonce=secrets.randbits(32)
            echoed,flags,uptime=fields(self.link(address).request(f'HEALTH {nonce:08X}',{'HEALTH'},timeout=self.reply_timeout,attempts=1),'HEALTH',3)
            if echoed!=nonce:raise UpdateError('Stale health reply')
            causes=[name for bit,name in ((29,'Watchdog'),(30,'Window watchdog'),(27,'Power-on'),(28,'Software reset'),(26,'Reset pin'),(31,'Low-power reset')) if flags&(1<<bit)]
            reply=self.link(address).request(f'FAULTINFO {nonce:08X}',{'FAULTINFO'},timeout=self.reply_timeout,attempts=1)
            echoed,fault,target,received,duration=fields(reply,'FAULTINFO',5)
            if echoed!=nonce:raise UpdateError('Stale fault reply')
            self.diagnostics[uid]=dict(reset_cause=' / '.join(causes) or 'Unavailable (bootloader clears reset flags)',reset_flags=flags,uptime_ms=uptime,
                fault_code=fault&255,target=target,received=received,duration_ms=duration,
                contact_closed=bool(fault&256),switch_no=bool(fault&512),peel_running=bool(fault&1024))
        except (OSError,TimeoutError,UpdateError) as error:
            self.diagnostics[uid]=dict(error=str(error)[:240])

    def bench_action(self,args,locate=False):
        address=integer(args['address'],1,99,'Address');uid=args.get('uid');action=args.get('action')
        if not isinstance(uid,str) or not re.fullmatch(r'[0-9A-F]{24}',uid):raise ValueError('Select an identified feeder')
        if not locate and action not in ('start','end','forward','reverse','peel','stop'):raise ValueError('Unknown loading action')
        if not self.bus.acquire(timeout=.5):raise ServiceError('Bus busy; action was not queued')
        try:
            if self.updating or (self.batch_update or {}).get('active'):raise ServiceError('Wait for the firmware update')
            if self.observe(address)!=uid:raise ServiceError('Feeder identity changed')
            # Owning the bus excludes in-flight feeds; subsequent OpenPnP feeds are paused.
            self.maintenance=True
            row=next(f for f in self.stock.rows() if f['uid']==uid)
            if not locate and action in ('forward','reverse'):
                if row['mode']!='load':raise ServiceError('Start tape loading first')
                result=self.feed(address,0,manual=True,expected_uid=uid,retract=action=='reverse')
                return dict(loading=True,moved=action,result=result)
            nonce=secrets.randbits(32)
            words=' '.join(uid[i:i+8] for i in (0,8,16))
            command=f'LOCATE {nonce:08X}' if locate else f'LOAD {nonce:08X} {words} '+f"{dict(end=0,start=1,peel=2,stop=3)[action]:08X}"
            try:reply=self.link(address).request(command,{'LOCATING' if locate else 'LOAD','BUSY'},timeout=self.reply_timeout,attempts=1)
            except TimeoutError as error:raise ServiceError('No action confirmation; firmware 0.1.4 is required for loading. Read status before retrying.') from error
            if reply.startswith('BUSY'):raise ServiceError('Feeder busy; finish its movement, test or menu first')
            values=fields(reply,'LOCATING' if locate else 'LOAD',1 if locate else 3)
            if values[0]!=nonce:raise ServiceError('Stale action confirmation')
            self.observe(address)
            return dict(locating=True) if locate else dict(loading=bool(values[1]),peeling=bool(values[2]))
        finally:self.bus.release()

    def cache_stock(self,uid,reply,nonce):
        echoed,quantity,advances,sequence=fields(reply,'STOCK',4)
        if echoed!=nonce or quantity>65535:raise UpdateError('Invalid stock reply')
        info=dict(available=True,remaining=None if quantity==65535 else quantity,
                  advances=advances,sequence=sequence,read_at=time.time())
        self.stock_caps[uid]=True
        self.stock.save_details(uid,'stock',info)
        return info

    def read_stock(self,address,uid):
        nonce=secrets.randbits(32)
        try:
            reply=self.link(address).request(f'STOCKREAD {nonce:08X}',{'STOCK'},timeout=self.reply_timeout,attempts=1)
            return self.cache_stock(uid,reply,nonce)
        except (OSError,TimeoutError,UpdateError) as error:
            previous=next((r.get('stock') or {} for r in self.stock.rows() if r['uid']==uid),{})
            info=dict(previous,available=previous.get('available',False),error=str(error)[:240])
            self.stock_caps[uid]=info['available']
            self.stock.save_details(uid,'stock',info)
            return info

    def save_configuration(self, args):
        address = integer(args['address'],0,99,'Address')
        expected_uid = args.get('uid','')
        if not isinstance(expected_uid,str) or not re.fullmatch(r'[0-9A-F]{24}',expected_uid):
            raise ValueError('Select an identified feeder first')
        keys = ('feed_reverse','peel_reverse','switch_no')
        if any(type(args.get(k)) is not bool for k in keys): raise ValueError('Provide all motor/switch settings')
        if not self.bus.acquire(blocking=False): raise ServiceError('Bus busy; settings were not queued')
        try:
            with self.control:
                if not self.maintenance or self.updating or (self.batch_update or {}).get('active'): raise ServiceError('Pause feeders and finish updates before saving hardware settings')
            uid = self.observe(address)
            if uid != expected_uid: raise ServiceError('Feeder identity changed; select it again')
            row = next(f for f in self.stock.rows() if f['uid']==uid)
            repair=row['fault_code']==3
            if row['mode']!='normal' or (row['state']!='idle' and not repair) or (row['fault_code'] and not repair):
                raise ServiceError('Feeder must be idle and fault-free before saving settings')
            width=args.get('width',int(row['variant'].removesuffix('mm')) if row['configured'] else 0)
            if type(width) is not int or width not in (8,12,16,24):raise ValueError('Select width 8, 12, 16 or 24 mm')
            count = events_for_pitch(args['pitch_mm'],2000 if width==8 else 4000)
            nonce=secrets.randbits(32);link=self.link(address)
            before=read_options(link,nonce)
            hardware_uid=tuple(int(uid[i:i+8],16) for i in (0,8,16))
            options = tuple(int(args[k]) for k in keys)
            try:
                if options != before or repair: save_options(link,hardware_uid,options,nonce)
                if not row['configured'] or int(row['variant'].removesuffix('mm'))!=width:
                    body='SETTYPE '+' '.join(f'{v:08X}' for v in (nonce,*hardware_uid,width))
                    try:link.request(body,{'TYPESET'},attempts=1,expected=f'TYPESET {nonce:08X} {width:08X}')
                    except TimeoutError:pass
                    result=fields(link.request(f'TYPE {nonce:08X}',{'TYPE'}),'TYPE',4)
                    if result[:2]!=(nonce,width):raise ServiceError('Saved width did not verify')
                if count != row['default_count']: set_count(self.port,address,count,uid=hardware_uid)
                if repair:self.clear_error(dict(address=address,uid=uid))
                self.stock.load(uid,row['label'],None,count,row['low'])
            except (OSError,TimeoutError,UpdateError) as error:
                raise ServiceError('Settings may be partly saved; read them before retrying: '+str(error)) from error
            finally:
                self.read_details(address)
        finally: self.bus.release()

    def clear_error(self, args):
        address=integer(args['address'],1,99,'Address')
        uid=args.get('uid')
        if not isinstance(uid,str) or not re.fullmatch(r'[0-9A-F]{24}',uid):
            raise ValueError('Select an identified feeder')
        if not self.bus.acquire(timeout=.5):raise ServiceError('Bus busy; clear was not queued')
        try:
            with self.control:
                if self.updating or (self.batch_update or {}).get('active'):
                    raise ServiceError('Wait for the firmware update to finish')
                self.maintenance=True
            if self.observe(address)!=uid:raise ServiceError('Feeder identity changed; select it again')
            nonce=secrets.randbits(32)
            words=' '.join(uid[i:i+8] for i in range(0,24,8))
            try:
                reply=self.link(address).request(f'CLEAR {nonce:08X} {words}',{'CLEARED','BUSY'},
                                                     timeout=self.reply_timeout,attempts=1)
            except TimeoutError as error:
                raise ServiceError('No clear confirmation. Firmware 0.1.3 is required; inspect feeder status before retrying.') from error
            if reply.startswith('BUSY'):raise ServiceError('Feeder busy; finish its movement or menu first')
            if fields(reply,'CLEARED',1)!=(nonce,):raise ServiceError('Stale clear confirmation')
            self.observe(address)
            return dict(cleared=True)
        finally:self.bus.release()

    def test_inputs(self, args):
        """0.1.2 firmware inhibits both motors; reads never enable test/motion."""
        address = integer(args['address'], 1, 99, 'Address')
        uid = args.get('uid')
        action = args.get('action')
        if not isinstance(uid,str) or not re.fullmatch(r'[0-9A-F]{24}',uid):
            raise ValueError('Select an identified feeder')
        if action not in ('start','read','end'): raise ValueError('Unknown test action')
        if not self.bus.acquire(timeout=.5): raise ServiceError('Bus busy; test command was not queued')
        try:
            with self.control:
                if self.updating or (self.batch_update and self.batch_update['active']):
                    raise ServiceError('Wait for the firmware update to finish')
                if action != 'read' and not self.maintenance:
                    raise ServiceError('Pause feeders before starting or ending a test')
            if self.observe(address) != uid:
                raise ServiceError('Feeder identity changed; select it again')
            nonce = secrets.randbits(32)
            link = self.link(address)
            def read_reply(command):
                reply=link.request(command,{'TEST','BUSY'},timeout=self.reply_timeout,attempts=1)
                if reply.startswith('BUSY'): raise ServiceError('Feeder is busy; finish its movement or menu first')
                values=fields(reply,'TEST',5)
                if values[0]!=nonce or values[1]&~255:raise UpdateError('Invalid test reply')
                return values
            test_sent=False
            try:
                # Capability/read probe first: older firmware receives no new state command.
                values=read_reply(f'TESTREAD {nonce:08X}')
                if action!='read' and bool(values[1]&1)!=(action=='start'):
                    target=int(action=='start')
                    nonce=secrets.randbits(32)
                    test_sent=True
                    values=read_reply(f'TEST {nonce:08X} {uid[:8]} {uid[8:16]} {uid[16:]} {target:08X}')
                    if bool(values[1]&1)!=bool(target):raise UpdateError('Test mode was not confirmed')
            except (TimeoutError,UpdateError) as error:
                raise ServiceError(('Test command not confirmed; motors may remain inhibited. Read inputs again. ' if test_sent else 'Input tests require firmware 0.1.2; no test-start command was sent. ')+str(error)) from error
            flags=values[1]
            result=dict(address=address,uid=uid,active=bool(flags&1),contact_closed=bool(flags&2),
                        peel_requested=bool(flags&4),peel_running=bool(flags&8),index_running=bool(flags&16),
                        feed_button_pressed=bool(flags&32),menu_button_pressed=bool(flags&64),
                        index_sensor_high=bool(flags&128),switch_changes=values[2],uptime_ms=values[3],
                        sensor_total=values[4],read_at=time.time())
            if result['active'] and (result['peel_running'] or result['index_running']):
                raise ServiceError('Unexpected motor state during test; inspect feeder before continuing')
            if action!='read':self.observe_safely(address)
            return result
        finally:self.bus.release()

    def set_maintenance(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("enabled must be true or false")
        with self.control:
            if (self.updating or (self.batch_update and self.batch_update['active'])) and not enabled:
                raise ServiceError("Wait for the firmware upload to finish")
            if not enabled and any(r['mode'] in ('test','load') for r in self.stock.rows()):
                raise ServiceError('End feeder input tests and tape loading before resuming feeders')
            self.maintenance = enabled

    def _identity(self, address, nonce):
        link = self.link(address)
        reply = link.request(f"IDENT {nonce:08X}", {"IDENT"}, timeout=self.reply_timeout, attempts=1)
        values = fields(reply, "IDENT", 5)
        if values[0] != nonce:
            raise UpdateError("Stale identity reply")
        return "".join(f"{n:08X}" for n in values[1:4])

    def observe(self, address):
        """Caller holds bus; inventory failures never change motor state."""
        nonce = secrets.randbits(32)
        known=next((row for row in self.stock.rows() if row['address']==address),None)
        link = self.link(address)
        reply = link.request(f"DIAG {nonce:08X}", {"DIAG"}, timeout=self.reply_timeout, attempts=1)
        values = fields(reply, "DIAG", 5)
        if values[0] != nonce:
            raise UpdateError("Stale diagnostic reply")
        reported_token=f"{values[1]:08X}{values[2]:08X}"
        # Runtime token changes on reboot/replacement. Read UID only on discovery,
        # reboot or reconnect; ordinary heartbeats need one DIAG exchange.
        stale_after=max(5,len(self.ids)*(self.background_interval+self.reply_timeout)*2)
        uid=(known['uid'] if known and known['token']==reported_token and not known['error']
             and known['age_seconds']<=stale_after else self._identity(address,nonce))
        if not (values[1] | values[2]):
            token = secrets.randbits(64) or 1
            reply = link.request(f"MONITOR {nonce:08X} {token >> 32:08X} {token & 0xFFFFFFFF:08X}",
                                 {"DIAG"}, timeout=self.reply_timeout, attempts=1)
            values = fields(reply, "DIAG", 5)
            if values[0] != nonce or not (values[1] | values[2]):
                raise UpdateError("Telemetry token was not claimed")
        token = f"{values[1]:08X}{values[2]:08X}"
        self.bootloaders.pop(address,None)
        if known and known['uid']==uid and known['token']!=token:
            previous=self.reboots.get(uid,{})
            self.reboots[uid]=dict(count=previous.get('count',0)+1,at=time.time())
        delta=self.stock.observe(address, uid, token, values[3], values[4])
        if self.stock_caps.get(uid) and (not known or known['token']!=token or known['counter']!=values[3]):
            self.read_stock(address,uid)
        reported=state_fields(values[4])
        if uid not in self.diagnostics or not known or known['token']!=token or known['fault_code']!=reported['fault_code']:
            self.read_diagnostics(address,uid)
        with self.control:
            prior=self.activities.get(address)
        tcp_active=address in self.active_feeds or (prior and prior['source']=='tcp' and prior['stage']=='failed' and prior['expires']>time.time())
        if reported['state'] in ('reserved','running') and not tcp_active:
            self.record_activity(address,'advancing','Advancing','device',hold=2)
        elif delta and not tcp_active:
            self.record_activity(address,'observed','Movement detected','sensor',hold=3)
        elif reported['state']=='idle' and prior and prior['source']=='device' and prior['stage']=='advancing':
            self.record_activity(address,'observed','Movement detected','sensor',hold=3)
        with self.control:
            self.errors.pop(address, None)
        return uid

    def observe_safely(self, address):
        try:
            return self.observe(address)
        except Exception as error:
            # Telemetry/inventory is optional: even a damaged database must not
            # turn a sensor-confirmed DONE into an OpenPnP error.
            message = str(error)[:240]
            # Only remembered hardware gets a recovery probe, not every empty ID.
            if isinstance(error,TimeoutError) and any(r['address']==address for r in self.stock.rows()):
                try:
                    self.loader_ready(address)
                    self.bootloaders[address]=time.monotonic()
                    message='Bootloader: ready for firmware update'
                except (OSError,TimeoutError,UpdateError):self.bootloaders.pop(address,None)
            with self.control:
                changed = self.errors.get(address) != message
                self.errors[address] = message
            if changed:
                log.warning("ID %s telemetry: %s", address, message)
            try:
                self.stock.failed(address, error)
            except Exception:
                log.exception("Could not record inventory error; feeding is independent")
            return None

    def loader_ready(self,address):
        reply=self.link(address).request('HELLO',{'READY'},timeout=self.reply_timeout,attempts=1)
        if fields(reply,'READY',3)!=(3,0x08002000,APP_MAX):raise UpdateError('Unexpected bootloader reply')

    def _motion_reply(self, address, tokens, deadline):
        while time.monotonic() < deadline:
            raw = self.port.read_until(b"\n", 129)
            self.startup_packet(raw)
            body = decode_packet(raw, address)
            if body is None:
                continue
            label = body.split(" ", 1)[0]
            if label not in {"ACCEPT", "BUSY", "RUNNING", "DONE", "FAULT", "UNKNOWN"}:
                continue
            try:
                if fields(body, label, 2) == tokens:
                    return label
            except UpdateError:
                continue
        return None

    def feed(self, address, count, manual=False, expected_uid=None, retract=None):
        integer(address, 1, 99, "Feeder ID")
        integer(count, 0, 99, "Feed count")
        if retract is not None and (not manual or type(retract) is not bool):raise ValueError("Invalid loading move")
        source="web" if manual else "tcp"
        with self.control:
            if self.maintenance and not manual:
                raise ServiceError("Maintenance mode: advance rejected")
        if not self.bus.acquire(timeout=1):
            raise ServiceError("Bus busy: advance rejected before transmission")
        try:
            with self.control:
                if manual:
                    if not self.maintenance or self.updating or (self.batch_update or {}).get('active'):
                        raise ServiceError('Pause feeder commands before a manual advance')
                    if not expected_uid or self.observe(address)!=expected_uid:raise ServiceError('Feeder identity changed')
                elif self.maintenance:
                    raise ServiceError("Maintenance mode: advance rejected")
            # Stock is deliberately absent from this acceptance decision.
            self.sequence = (self.sequence + 1) & 0xFFFFFFFF
            if not self.sequence:
                self.session, self.sequence = secrets.randbits(32), 1
            tokens = (self.session, self.sequence)
            text = f"{tokens[0]:08X} {tokens[1]:08X}"
            deadline = time.monotonic() + self.feed_timeout
            try:
                # Never retry FEED, including write/ack failures: it may have moved.
                with self.control:self.active_feeds.add(address)
                self.record_activity(address,'requested','Starting',source=source,hold=self.feed_timeout+2)
                self.port.write(packet(address, f"FEED {text} {count:08X}" if retract is None else f"JOG {text} {int(retract):08X} 00000001"))
                self.port.flush()
                result = self._motion_reply(address, tokens, min(deadline, time.monotonic() + self.reply_timeout))
                while True:
                    if result in ('ACCEPT','RUNNING'):
                        self.record_activity(address,'advancing','Advancing',source=source,hold=self.feed_timeout+2)
                    if result == "DONE":
                        self.record_activity(address,'completed','Advanced',source=source,hold=3)
                        return f"ok N{address} F{count}"
                    if result in {"BUSY", "FAULT", "UNKNOWN"}:
                        raise ServiceError(f"ID {address}: {result.lower()}; advance not confirmed")
                    if time.monotonic() >= deadline:
                        raise ServiceError(f"ID {address}: completion timeout; do not resend automatically")
                    self.port.write(packet(address, f"STATUS {text}"))
                    self.port.flush()
                    result = self._motion_reply(address, tokens, min(deadline, time.monotonic() + self.reply_timeout))
                    if result not in {"DONE", "BUSY", "FAULT", "UNKNOWN"}:
                        time.sleep(self.poll_interval)
            except Exception as error:
                self.record_activity(address,'failed','Advance unconfirmed',source=source,hold=10,error=str(error)[:240])
                raise
            finally:
                # Even if telemetry/SQLite fails after DONE, the confirmed feed
                # still returns ok. Partial movement after faults is also counted.
                self.observe_safely(address)
                with self.control:self.active_feeds.discard(address)
        finally:
            self.bus.release()

    def load_stock(self, address, label, quantity=None, pitch=None, low=50, part_spacing_mm=None, expected_uid=None):
        integer(address, 0, 99, "Address")
        # Validate before any serial operation or baseline changes.
        if quantity is not None:integer(quantity, 0, 65534, "Loaded quantity")
        if part_spacing_mm is None:integer(pitch, 1, 99, "Pulses per part")
        elif pitch is not None:raise ValueError("Provide part spacing or pulses per part, not both")
        integer(low, 0, 1_000_000_000, "Low-stock threshold")
        if not isinstance(label, str) or len(label) > 128:
            raise ValueError("Invalid reel label")
        with self.bus:
            uid=self.observe(address)
            if expected_uid is not None and uid!=expected_uid:raise ServiceError('Feeder identity changed; reopen Reel / stock')
            if quantity is not None:
                info=self.read_stock(address,uid)
                if not info.get('available'):
                    raise ServiceError('Feeder-owned stock requires firmware 0.1.4; quantity was not saved')
                if info.get('error'):raise ServiceError('Could not read feeder stock: '+info['error'])
            if part_spacing_mm is not None:
                row=next(f for f in self.stock.rows() if f['uid']==uid)
                pitch=events_for_pitch(part_spacing_mm,row['nominal_step_um'])
                if pitch!=row['default_count']:
                    if not self.maintenance or self.updating or (self.batch_update or {}).get('active'):
                        raise ServiceError('Pause feeders before changing part spacing')
                    if row['state']!='idle' or row['mode']!='normal' or row['fault_code']:
                        raise ServiceError('Feeder must be idle and fault-free before changing spacing')
                    set_count(self.port,address,pitch,uid=tuple(int(uid[i:i+8],16) for i in (0,8,16)))
                    self.observe(address)
            if quantity is not None:
                nonce=secrets.randbits(32)
                words=' '.join(uid[i:i+8] for i in (0,8,16))
                try:
                    reply=self.link(address).request(f'SETSTOCK {nonce:08X} {words} {quantity:08X}',
                                                    {'STOCK','BUSY'},timeout=self.reply_timeout,attempts=1)
                    if reply.startswith('BUSY'):raise ServiceError('Feeder busy; quantity was not saved')
                    info=self.cache_stock(uid,reply,nonce)
                except TimeoutError:
                    info=self.read_stock(address,uid) # Read back; never resend a set.
                if info.get('error') or info.get('remaining')!=quantity or info.get('advances')!=0:
                    raise ServiceError('Quantity save not confirmed; read stock before retrying')
            self.stock.load(uid, label, None, pitch, low)
            return uid

    def sync_part(self, uid):
        with self.reel_lock:
            row=next((f for f in self.stock.rows() if f['uid']==uid),None)
            if not row or not row.get('part_assignment'):raise ValueError('No saved part assignment')
            assignment=dict(row['part_assignment'])
            try:
                address=integer(row['address'],1,99,'Bus ID')
                with self.bus:
                    if self.observe(address)!=uid:raise ServiceError('Feeder identity changed; part was not assigned')
                state=openpnp_request('/state')
                matches=[f for f in state.get('feeders',[]) if f.get('bus_id')==address]
                if len(matches)>1:raise ServiceError('Multiple powered feeders use this bus ID in OpenPnP')
                if matches:
                    result=openpnp_request('/action',dict(action='set_feeder_part',bus_id=address,
                                           feeder_id=matches[0]['id'],part_id=assignment['part_id']),timeout=30)
                else:
                    if not assignment['part_id']:raise ServiceError('Select a part to create this feeder in OpenPnP')
                    result=openpnp_request('/action',dict(action='add_feeder',bus_id=address,
                                           name='Feeder '+str(address),part_id=assignment['part_id']),timeout=30)
                actual=result.get('feeder',{})
                if not result.get('saved') or not actual.get('id') or actual.get('bus_id')!=address or actual.get('part_id')!=assignment['part_id'] or (matches and actual['id']!=matches[0]['id']):
                    raise ServiceError('OpenPnP part assignment was not confirmed; check before retrying')
                assignment.update(status='synced',error=None,feeder_id=actual['id'],synced_at=time.time())
            except (ServiceError,ValueError,OSError,TimeoutError) as error:
                assignment.update(status='pending',error=str(error)[:300])
            self.stock.save_details(uid,'part_assignment',assignment)
            return assignment


    def assign_id(self, address, new_id):
        integer(address, 0, 99, "Current address")
        integer(new_id, 1, 99, "New ID")
        with self.bus:
            with self.control:
                if not self.maintenance or self.updating or (self.batch_update or {}).get("active"):
                    raise ServiceError("Pause feeders and finish updates before assigning an ID")
            assign(self.port, address, new_id)
            with self.control:
                self.ids = sorted((set(self.ids) - {address}) | {new_id})
                self.stock.save_setting('polling_ids',self.ids)
                self.errors.pop(address, None)
            self.observe_safely(new_id)

    def update(self, address, image):
        integer(address, 0, 99, "Address")
        _, _, checksum = inspect_image(image)  # Validate before any BOOT/erase request.
        if not self.bus.acquire(blocking=False):
            raise ServiceError("Bus busy: firmware update was not started")
        try:
            with self.control:
                if not self.maintenance:
                    raise ServiceError("Enable maintenance before updating firmware")
                self.updating = True
                self.update_status = dict(address=address, stage="connecting", sent=0,
                                          size=len(image), crc32=f"{checksum:08X}",
                                          started=time.time(), error=None)
            def progress(stage, sent, total):
                with self.control:
                    self.update_status.update(stage=stage, sent=sent, size=total)
            succeeded = False
            try:
                upload(self.link(address), image, progress=progress)
                succeeded = True
            except Exception as error:
                with self.control:
                    self.update_status.update(stage="failed", error=str(error)[:240])
                raise
            finally:
                if succeeded:
                    # DONE precedes the application's startup flashes. Allow
                    # it to initialise before attempting optional telemetry.
                    deadline = time.monotonic() + 3
                    while not self.observe_safely(address) and time.monotonic() < deadline:
                        time.sleep(0.1)
                    try:
                        self.read_details(address)
                    except Exception:
                        pass  # Upload verification already succeeded; telemetry is optional.
                else:
                    self.observe_safely(address)
                with self.control:
                    self.updating = False
                    self.update_status["finished"] = time.time()
        finally:
            self.bus.release()

    def queue_update(self, image, address=None):
        _, _, checksum = inspect_image(image)
        if address is not None:integer(address,0,99,'Address')
        with self.control:
            if self.updating or (self.batch_update or {}).get('active'):
                raise ServiceError('An update is already running')
            targets=[dict(address=r['address'],uid=r['uid'],stage='queued',error=None)
                     for r in self.snapshot()['feeders'] if r['known'] and (r['online'] or address==r['address']) and r['address'] is not None
                     and (r['address'] if address is None else r['address']==address)
                     and (address is not None or r.get('bootloader') or (r.get('firmware_info') or {}).get('error')
                          or (r.get('firmware_info') or {}).get('crc32')!=f'{checksum:08X}'
                          or (r.get('firmware_info') or {}).get('size')!=len(image))]
            if not targets and address is not None:
                targets=[dict(address=address,uid=None,stage='queued',error=None)]
            if not targets:raise ServiceError('No online feeders need this firmware')
            self.maintenance=True
            self.batch_update=dict(active=True,started=time.time(),finished=None,items=targets,error=None)
        threading.Thread(target=self._update_batch,args=(image,checksum,targets),daemon=True).start()

    def _update_batch(self,image,checksum,targets):
        try:
            with self.bus:
                for target in targets:
                    try:
                        with self.control:target['stage']='checking'
                        try:uid=self.read_firmware(target['address'])
                        except TimeoutError:
                            # The existing loader has no UID command. Explicit
                            # recovery uses its addressed READY reply instead.
                            self.loader_ready(target['address'])
                            with self.control:target['stage']='updating'
                            self.update(target['address'],image)
                            with self.control:target['stage']='complete'
                            continue
                        if target['uid'] is not None and uid!=target['uid']:raise ServiceError('Feeder identity changed; update skipped')
                        info=next(r['firmware_info'] for r in self.stock.rows() if r['uid']==uid)
                        if not info.get('error') and info.get('crc32')==f'{checksum:08X}' and info.get('size')==len(image):
                            with self.control:target['stage']='current'
                            continue
                        with self.control:target['stage']='updating'
                        self.update(target['address'],image)
                        with self.control:target['stage']='complete'
                    except Exception as error:
                        with self.control:
                            target.update(stage='failed',error=str(error)[:240])
                            self.batch_update['error']=str(error)[:240]
        finally:
            with self.control:
                for target in targets:
                    if target['stage']=='queued':target['stage']='not_updated'
                self.batch_update.update(active=False,finished=time.time())

    def snapshot(self):
        with self.control:
            status = dict(version=VERSION, maintenance=self.maintenance, updating=self.updating,
                          polling_ids=list(self.ids), errors=dict(self.errors),
                          update=dict(self.update_status) if self.update_status else None,
                          batch_update=dict(self.batch_update,items=[dict(item) for item in self.batch_update['items']]) if self.batch_update else None,
                          stale_after_seconds=max(5, len(self.ids) *
                                                  (self.background_interval + self.reply_timeout) * 2))
        status["inventory_persistent"] = self.stock.persistent
        try:
            status["feeders"] = self.stock.rows()
        except Exception as error:
            status["feeders"], status["inventory_error"] = [], str(error)[:240]
        status['activity']=self.activity_snapshot()
        rows = status['feeders']
        for row in rows:
            row['known'] = True
            row['bootloader']=time.monotonic()-self.bootloaders.get(row['address'],-1e9)<max(5,len(self.ids)*(.5+self.reply_timeout))
            row['restart']=self.reboots.get(row['uid'])
            row['diagnostics']=self.diagnostics.get(row['uid'],{})
            row['online'] = bool(row['address'] in status['polling_ids'] and not row['error'] and
                                 row['age_seconds'] <= status['stale_after_seconds'])
            row['online'] |= row['bootloader']
        present = {row['address'] for row in rows}
        for address in status['polling_ids']:
            if address not in present:
                rows.append(dict(uid=None,address=address,known=False,online=False,variant='—',label='',loaded=None,
                                 remaining=None,low_stock=False,uncertain=False,age_seconds=None,seen=None,
                                 error=status['errors'].get(address,''),state='never_seen',mode='unknown',fault_code=0,
                                 fault='none',ready=False,assigned=bool(address),configured=False,firmware_info=None,
                                 configuration=None,default_count=None,nominal_step_um=0))
        rows.sort(key=lambda row:(row['address'] is None,row['address'] or 0,row['uid'] or ''))
        return status

    def poll(self, stopped, interval=0.01):
        self.background_interval=interval
        due={};details_seen={};details_due={};probe_at=0
        while not stopped.wait(interval):
            if not self.bus.acquire(blocking=False):continue
            try:
                now=time.monotonic()
                with self.control:ids=list(self.ids)
                # No request is in flight while we hold the bus here.
                if getattr(self.port,'in_waiting',0):
                    self.startup_packet(self.port.read_until(b'\n',129))
                arrivals=self.startup_ids.intersection(ids)
                for address in arrivals:
                    due[address]=0
                    details_seen.pop(address,None)
                known={r['address']:r for r in self.stock.rows()}
                ready=[a for a in ids if due.get(a,0)<=now]
                live=[a for a in ready if a in known and not known[a]['error']]
                probes=[a for a in ready if a not in live]
                if arrivals:
                    address=min(arrivals)
                    self.startup_ids.discard(address)
                elif probes and now>=probe_at:
                    address=min(probes,key=lambda a:(due.get(a,0),a));probe_at=now+.5
                elif live:address=min(live,key=lambda a:(due.get(a,0),a))
                else:continue
                uid=self.observe_safely(address)
                due[address]=time.monotonic()+(.5 if uid else 2)
                if uid:
                    row=next(r for r in self.stock.rows() if r['uid']==uid)
                    failed=any((row.get(k) or {}).get('error') for k in ('firmware_info','configuration')) or bool((row.get('stock') or {}).get('error') and ((row.get('stock') or {}).get('available') or (row.get('firmware_info') or {}).get('version')=='0.1.4'))
                    if details_seen.get(address)!=(uid,row['token']) or (failed and now>=details_due.get(address,0)):
                        self.read_details(address,uid)
                        details_seen[address]=(uid,row['token'])
                        details_due[address]=time.monotonic()+5
                else:details_seen.pop(address,None)
            except Exception:log.exception('Background feeder telemetry failed; feed requests remain independent')
            finally:self.bus.release()


class GcodeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, port, feeders):
        self.feeders, self.client = feeders, threading.Lock()
        super().__init__(("127.0.0.1", port), GcodeHandler)


class GcodeHandler(socketserver.StreamRequestHandler):
    def handle(self):
        if not self.server.client.acquire(blocking=False):
            self.wfile.write(b"error: another OpenPnP client is already connected\n")
            return
        try:
            while True:
                raw = self.rfile.readline(129)
                if not raw:
                    return
                if len(raw) > 128 or not raw.endswith(b"\n") or b"\0" in raw:
                    self.wfile.write(b"error: invalid/overlong command; connection closed\n")
                    return
                try:
                    text = raw.decode("ascii").strip()
                    if text.upper() == "M115":
                        reply = f"FIRMWARE_NAME:V485_USB_HOST FIRMWARE_VERSION:{VERSION}\nok"
                    elif text.upper() == "M400":
                        if self.server.feeders.maintenance:
                            raise ServiceError("Maintenance mode")
                        if not self.server.feeders.bus.acquire(timeout=1):
                            raise ServiceError("Bus busy")
                        try:
                            reply = "ok"
                        finally:
                            self.server.feeders.bus.release()
                    else:
                        match = re.fullmatch(r"(?:M600[ \t]+)?N([0-9]{1,2})[ \t]+F([0-9]{1,2})", text, re.I)
                        if not match:
                            raise ValueError("expected M600 N1..99 F0..99")
                        reply = self.server.feeders.feed(int(match[1]), int(match[2]))
                except (UnicodeError, ValueError, ServiceError, UpdateError, OSError, TimeoutError) as error:
                    reply = "error: " + str(error).replace("\n", " ").replace("\r", " ")
                self.wfile.write((reply + "\n").encode("ascii", errors="replace"))
                self.wfile.flush()
        except OSError:
            # An in-flight feed is never replayed after a broken TCP connection.
            log.info("OpenPnP connection closed")
        finally:
            self.server.client.release()


class WebServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, feeders, demo=False, tcp_port=5001, host="127.0.0.1"):
        self.events_stopped=threading.Event()
        self.feeders, self.demo, self.tcp_port = feeders, demo, tcp_port
        super().__init__((host, port), WebHandler)
    def server_close(self):
        self.events_stopped.set()
        if hasattr(self.feeders,'activity_condition'):
            with self.feeders.activity_condition:self.feeders.activity_condition.notify_all()
        super().server_close()


class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def respond(self, status, value, content_type="application/json"):
        data = json.dumps(value).encode() if content_type == "application/json" else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def stream_activity(self):
        service=self.server.feeders
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream')
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        try:
            with service.control:
                revision=service.activity_revision
                initial=service.activity_snapshot()
            self.wfile.write((f'id: {revision}\nevent: activity\ndata: '+json.dumps(initial)+'\n\n').encode())
            self.wfile.flush()
            while not self.server.events_stopped.is_set():
                with service.activity_condition:
                    events=[dict(e) for e in service.activity_events if e['id']>revision]
                    if not events and not self.server.events_stopped.is_set():
                        service.activity_condition.wait(10)
                        events=[dict(e) for e in service.activity_events if e['id']>revision]
                    revision=service.activity_revision
                if self.server.events_stopped.is_set():break
                payload=dict(server_time=time.time(),activities=events)
                message=(f'id: {revision}\nevent: activity\ndata: '+json.dumps(payload)+'\n\n') if events else ': keepalive\n\n'
                self.wfile.write(message.encode());self.wfile.flush()
        except (OSError,TimeoutError):pass
        self.close_connection=True

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in {"/", "/parts", "/packages", "/job", "/firmware", "/settings"}:
            self.respond(200, Path(__file__).with_name("dashboard.html").read_bytes(), "text/html; charset=utf-8")
        elif path == '/api/catalogue':
            try:
                if self.server.demo:self.respond(200,dict(online=False,api_version=1));return
                catalogue=openpnp_request('/state')
                # The existing unversioned companion has this same catalogue schema.
                if catalogue.setdefault('api_version',1)!=1:raise ServiceError('Reload OpenPnP-Web.py to match this dashboard')
                self.respond(200,catalogue)
            except ServiceError as error:self.respond(503,dict(error=str(error)))
        elif path == '/api/job':
            try:
                if self.server.demo:raise ServiceError('Job check requires OpenPnP')
                self.respond(200,job_stock(openpnp_request('/job',timeout=15),self.server.feeders.snapshot()))
            except (ServiceError,ValueError) as error:self.respond(409,dict(error=str(error)))
        elif path == '/api/events':
            self.stream_activity()
        elif path == "/api/status":
            status = self.server.feeders.snapshot()
            try:
                status['available_firmware'] = dict(read_bundle(BUNDLE)[0], available=True)
            except (OSError, ValueError, KeyError, TypeError) as error:
                status['available_firmware'] = dict(available=False, error='Built firmware unavailable: '+str(error))
            status["demo"] = self.server.demo
            status["tcp_port"] = self.server.tcp_port
            self.respond(200, status)
        else:
            self.respond(404, {"error": "Unknown path"})

    def do_POST(self):
        try:
            # Match the page's actual hostname/IP, including the implicit HTTP
            # port 80. LAN clients need no login; unrelated sites cannot POST.
            origin = self.headers.get("Origin")
            if origin:
                source = urlsplit(origin)
                target = urlsplit("http://" + self.headers.get("Host", ""))
                if (source.scheme != "http" or not source.hostname or source.username or source.password
                        or source.path or source.query or source.fragment
                        or (source.hostname, source.port or 80) != (target.hostname, target.port or 80)):
                    self.respond(403, {"error": "Use the feeder page on this host"})
                    return
            path = urlsplit(self.path)
            size = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= size <= APP_MAX:
                self.close_connection = True
                self.respond(413, {"error": "Missing or oversized request body"})
                return
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError("Incomplete request")
            feeders = self.server.feeders
            if path.path in {"/api/update", "/api/image"}:
                if self.headers.get_content_type() != "application/octet-stream":
                    raise ValueError("Send a firmware.bin as application/octet-stream")
                if path.path == "/api/image":
                    variant, size, checksum = inspect_image(raw)
                    self.respond(200, dict(variant=variant, size=size, crc32=f"{checksum:08X}"))
                    return
                if self.server.demo:
                    raise ServiceError("Demo mode cannot flash firmware")
                params = parse_qs(path.query)
                if set(params) != {"address"} or len(params["address"]) != 1:
                    raise ValueError("One address is required")
                feeders.queue_update(raw,int(params["address"][0]))
            else:
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("Use application/json")
                args = json.loads(raw)
                if not isinstance(args, dict):
                    raise ValueError("Expected a JSON object")
                if path.path == '/api/openpnp':
                    if self.server.demo:
                        raise ServiceError('Demo mode cannot control a real OpenPnP instance')
                    if args.get('action') not in {'add_feeder','edit_part','edit_package','create_part','create_package'}:
                        raise ValueError('Unknown feeder setup action')
                    self.respond(200, openpnp_request('/action', args, timeout=30))
                    return
                elif path.path in {'/api/update-bundled','/api/update-all-bundled'}:
                    if self.server.demo:
                        raise ServiceError('Demo mode cannot flash firmware')
                    metadata, image = read_bundle(BUNDLE)
                    if args.get('sha256') != metadata['sha256']:
                        raise ServiceError('Available firmware changed; refresh before updating')
                    feeders.queue_update(image,None if path.path=='/api/update-all-bundled' else integer(args['address'],0,99,'Address'))
                elif path.path == '/api/clear-error':
                    self.respond(200,feeders.clear_error(args));return
                elif path.path in ('/api/loading','/api/locate'):
                    self.respond(200,feeders.bench_action(args,locate=path.path=='/api/locate'));return
                elif path.path == '/api/advance':
                    address=integer(args['address'],1,99,'Address')
                    result=feeders.feed(address,0,manual=True,expected_uid=args.get('uid'))
                    self.respond(200,dict(advanced=True,result=result));return
                elif path.path == '/api/test':
                    self.respond(200,feeders.test_inputs(args));return
                elif path.path == "/api/maintenance":
                    feeders.set_maintenance(args["enabled"])
                elif path.path == "/api/polling":
                    ids = parse_ids(args["ids"])
                    with feeders.control:
                        feeders.ids = ids
                        feeders.stock.save_setting('polling_ids',ids)
                elif path.path == "/api/refresh":
                    address = integer(args["address"], 0, 99, "Address")
                    feeders.read_details(address)
                elif path.path == "/api/configure":
                    feeders.save_configuration(args)
                elif path.path == '/api/part-sync':
                    if self.server.demo:raise ServiceError('Demo mode cannot change OpenPnP parts')
                    self.respond(200,dict(part_assignment=feeders.sync_part(args['uid'])))
                    return
                elif path.path == "/api/stock":
                    with feeders.reel_lock:
                        if 'part_id' in args:
                            if self.server.demo:raise ServiceError('Demo mode cannot change OpenPnP parts')
                            if not isinstance(args['part_id'],str) or len(args['part_id'])>512:raise ValueError('Invalid part ID')
                            if not isinstance(args.get('uid'),str) or not re.fullmatch(r'[0-9A-F]{24}',args['uid']):raise ValueError('Select an identified feeder')
                        uid=feeders.load_stock(args["address"], args.get("label", ""), args.get("quantity"),
                                           args.get("pulses_per_part"), args.get("low", 50), args.get("part_spacing_mm"),args.get('uid'))
                        if 'part_id' in args:
                            feeders.stock.save_details(uid,'part_assignment',dict(part_id=args['part_id'],status='pending',error=None))
                            self.respond(200,dict(ok=True,part_assignment=feeders.sync_part(uid)))
                            return
                elif path.path == "/api/assign":
                    feeders.assign_id(args["address"], args["new_id"])
                else:
                    self.respond(404, {"error": "Unknown path"})
                    return
            self.respond(200, {"ok": True})
        except (ValueError, KeyError, TypeError) as error:
            self.respond(400, {"error": str(error)})
        except ServiceError as error:
            self.respond(409, {"error": str(error)})
        except (OSError, TimeoutError, UpdateError) as error:
            self.respond(503, {"error": str(error)})
        except sqlite3.Error:
            log.exception("Inventory database operation failed")
            self.respond(500, {"error": "Inventory database error; inspect the service log"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--serial", help="Direct USB-RS485 port, e.g. COM5 or /dev/serial/by-id/...")
    source.add_argument("--demo", action="store_true", help="Simulated feeders; opens no hardware port")
    parser.add_argument("--ids", default="1-24", help="Polling addresses, e.g. 0,1-24 (one unassigned module only)")
    parser.add_argument("--database", type=Path, help="Stock database (default: ~/.v485/stock.sqlite3; separate demo-stock.sqlite3 in demo)")
    parser.add_argument("--tcp-port", type=int, default=5001)
    parser.add_argument("--web-host", default="0.0.0.0", help="HTTP bind address (default: all IPv4 interfaces)")
    parser.add_argument("--web-port", type=int, default=80, help="HTTP port (default: 80)")
    parser.add_argument("--poll-interval", type=float, default=0.01, help="Seconds between reads of responding modules; offline IDs are probed in the background")
    args = parser.parse_args()
    try:
        ids = parse_ids(args.ids)
        if not 0.01 <= args.poll_interval <= 60:
            raise ValueError("Poll interval must be 0.01..60 seconds")
        for port in (args.tcp_port, args.web_port):
            integer(port, 1, 65535, "Listen port")
        if len({args.tcp_port, args.web_port}) != 2:
            raise ValueError("Feeder TCP and web ports must differ")
    except ValueError as error:
        parser.error(str(error))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.database is None:
        args.database = Path.home() / ".v485" / ("demo-stock.sqlite3" if args.demo else "stock.sqlite3")
    try:
        args.database.parent.mkdir(parents=True, exist_ok=True)
        stock = Stock(args.database)
    except (OSError, sqlite3.Error):
        log.exception("Inventory storage unavailable; using temporary stock data, feeding remains enabled")
        stock = Stock(":memory:")
    stopped = threading.Event()
    servers = []
    port = None
    try:
        if args.demo:
            from simulated_bus import SimulatedBus
            port = SimulatedBus()
        else:
            import serial
            # Windows serial opens are exclusive; POSIX needs this explicit flag.
            options = {"exclusive": True} if os.name == "posix" else {}
            port = serial.Serial(args.serial, BAUD, timeout=0.05, write_timeout=2, **options)
            port.reset_input_buffer()
        feeders = Feeders(port, stock, ids)
        servers.append(GcodeServer(args.tcp_port, feeders))
        servers.append(WebServer(args.web_port, feeders, args.demo, args.tcp_port, args.web_host))
        for server in servers:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
        poller = threading.Thread(target=feeders.poll, args=(stopped, args.poll_interval), daemon=True)
        poller.start()
        web_name = socket.gethostname() if args.web_host == "0.0.0.0" else args.web_host
        web_suffix = "" if args.web_port == 80 else f":{args.web_port}"
        log.info("%sOpenPnP TCP 127.0.0.1:%s; feeder page http://%s%s (bind %s:%s)",
                 "DEMO: " if args.demo else "", args.tcp_port, web_name, web_suffix,
                 args.web_host, args.web_port)
        try:
            while not stopped.wait(1):
                pass
        except KeyboardInterrupt:
            log.info("Stopping; no motion requests will be replayed")
        finally:
            stopped.set()
            feeders.set_maintenance(True)
            for server in servers:
                server.shutdown()
            # Closing a hardware handle wakes serial reads. All motion remains
            # bounded by the MCU's own sensor count/deadline if the PC exits.
            port.close()
            poller.join(timeout=2)
    except (OSError, ImportError) as error:
        parser.exit(1, f"Could not start host: {error}\n")
    finally:
        for server in servers:
            server.server_close()
        if port is not None:
            port.close()
        # Request threads are daemons; avoid closing their SQLite connection
        # underneath a final in-flight telemetry write during process shutdown.


if __name__ == "__main__":
    main()
