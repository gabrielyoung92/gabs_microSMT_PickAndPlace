#!/usr/bin/env python3
"""Regression checks for the 0.1.3 review fixes; no physical hardware/profile."""
from pathlib import Path
import tempfile
import http.client
import json
import threading
import time
from unittest.mock import patch

import host_service as host
from check_host import sample_image, expect_error
from simulated_bus import SimulatedBus


def fixture(path=':memory:',port=None):
    port=port or SimulatedBus();port.nodes[1]['default']=2;stock=host.Stock(path)
    service=host.Feeders(port,stock,[1,2],reply_timeout=.005)
    uid=service.observe(1);service.read_details(1,uid)
    return port,stock,service,uid


def main():
    port,stock,s,uid=fixture()
    row=lambda:next(r for r in stock.rows() if r['uid']==uid)
    # An actual spacing change needs pause and writes the hardware before stock.
    expect_error(lambda:s.load_stock(1,'Reel',100,part_spacing_mm=8))
    assert row()['loaded'] is None
    s.set_maintenance(True)
    s.load_stock(1,'Reel',100,part_spacing_mm=8)
    assert port.nodes[1]['default']==row()['pitch']==row()['default_count']==4
    port.completed(1,10);s.observe(1)
    assert row()['remaining']==90
    s.load_stock(1,'Renamed',part_spacing_mm=8)
    assert row()['remaining']==90 and row()['used_pulses']==40
    s.load_stock(1,'New spacing',part_spacing_mm=4)
    assert row()['remaining']==90 and port.nodes[1]['default']==2
    s.load_stock(1,'Replenished',200,part_spacing_mm=4)
    assert row()['remaining']==200
    # Invalid options must be rewritten even when requested bits equal readback.
    port.nodes[1].update(fault=3,invalid_settings=True)
    args=dict(address=1,uid=uid,feed_reverse=False,peel_reverse=False,switch_no=False,pitch_mm=8,width=12)
    s.save_configuration(args)
    assert row()['fault_code']==0 and port.nodes[1]['width']==12 and row()['pitch']==2
    assert any(body.startswith('SETCONFIG ') for _,body in port.frames)
    assert s.maintenance
    # Commission an unconfigured width through the same settings save.
    port.nodes[1]['width']=0;s.observe(1)
    s.save_configuration(dict(args,width=8,pitch_mm=4))
    assert row()['variant']=='8mm' and row()['default_count']==2
    # Manual feed uses the same no-replay path; OpenPnP stays blocked by pause.
    expect_error(lambda:s.feed(1,0))
    expect_error(lambda:s.feed(1,0,manual=True,expected_uid='F'*24))
    before=port.feeds
    assert s.feed(1,0,manual=True,expected_uid=uid).startswith('ok ')
    assert port.feeds==before+1 and s.maintenance
    s.set_maintenance(False)
    expect_error(lambda:s.feed(1,0,manual=True,expected_uid=uid))
    port.nodes[1]['token']=(0,0);s.observe(1)
    assert s.snapshot()['feeders'][0]['restart']['count']==1
    s.observe(1);assert s.reboots[uid]['count']==1
    web=host.WebServer(0,s,demo=True);thread=threading.Thread(target=web.serve_forever,daemon=True);thread.start()
    def post(path,args):
        connection=http.client.HTTPConnection('127.0.0.1',web.server_port,timeout=3)
        connection.request('POST',path,json.dumps(args),{'Content-Type':'application/json'})
        response=connection.getresponse();value=response.status,json.loads(response.read());connection.close();return value
    try:
        s.set_maintenance(True)
        assert post('/api/advance',dict(address=1,uid=uid))[1]['advanced']
        remaining=row()['remaining']
        assert post('/api/stock',dict(address=1,uid=uid,label='HTTP rename',part_spacing_mm=4))[0]==200
        assert row()['remaining']==remaining
        s.set_maintenance(False)
        assert post('/api/advance',dict(address=1,uid=uid))[0]==409
    finally:web.shutdown();web.server_close();thread.join(1);stock.close()
    # Assignments persist the changed polling list across a host restart.
    with tempfile.TemporaryDirectory() as directory:
        port,stock,s,uid=fixture(Path(directory)/'stock.sqlite3')
        stock.save_setting('polling_ids',[1,2]);s.set_maintenance(True)
        port.nodes[1]['armed']=True;s.assign_id(1,3)
        assert host.Feeders(port,stock,[1,2],reply_timeout=.005).ids==[2,3]
        stock.close()
    # Existing loader recovery must work without an application DIAG or UID.
    class RecoveryBus(SimulatedBus):
        recovery=False
        def write(self,raw):
            address=int(raw[1:3]);body=host.decode_packet(raw,address)
            if self.recovery and address==1:
                if body=='HELLO':self.rx.append(host.packet(1,'READY 00000003 08002000 0000E000'))
                return len(raw)
            return super().write(raw)
    port,stock,s,uid=fixture(port=RecoveryBus());port.recovery=True
    assert s.observe_safely(1) is None
    assert s.snapshot()['feeders'][0]['bootloader']
    calls=[]
    def upload(link,image,progress):
        calls.append(link.address);port.recovery=False
        port.nodes[1].update(image_crc=host.inspect_image(image)[2],image_size=len(image))
        progress('complete',len(image),len(image))
    with patch.object(host,'upload',upload):
        s.queue_update(sample_image(),1)
        deadline=time.monotonic()+2
        while s.batch_update['active']:
            assert time.monotonic()<deadline;time.sleep(.005)
    assert calls==[1] and s.batch_update['items'][0]['stage']=='complete'
    assert not s.snapshot()['feeders'][0]['bootloader']
    assert s.maintenance
    # Explicit recovery also works before a unit has ever entered inventory.
    stock.close();stock=host.Stock(':memory:');s=host.Feeders(port,stock,[1],reply_timeout=.005)
    port.recovery=True
    with patch.object(host,'upload',upload):
        s.queue_update(sample_image(),1)
        deadline=time.monotonic()+2
        while s.batch_update['active']:
            assert time.monotonic()<deadline;time.sleep(.005)
    assert calls==[1,1] and s.batch_update['items'][0]['stage']=='complete'
    stock.close()
    # Successful DIAGs must not hide a failed metadata read forever.
    class NoisyBus(SimulatedBus):
        drop=False
        def write(self,raw):
            body=host.decode_packet(raw,int(raw[1:3]))
            if self.drop and body.startswith('CONFIG '):return len(raw)
            return super().write(raw)
    port,stock,s,uid=fixture(port=NoisyBus());port.drop=True
    stop=threading.Event();worker=threading.Thread(target=s.poll,args=(stop,.002),daemon=True);worker.start()
    try:
        deadline=time.monotonic()+1
        while not stock.rows()[0]['configuration'].get('error'):
            assert time.monotonic()<deadline;time.sleep(.005)
        port.drop=False;deadline=time.monotonic()+7
        while stock.rows()[0]['configuration'].get('error'):
            assert time.monotonic()<deadline;time.sleep(.01)
        assert port.feeds==0
    finally:stop.set();worker.join(1);stock.close()
    print('0.1.3 fixes passed: actual pitch, preserved stock, E3 recovery, width, manual feed, restart indicator, persistent IDs, loader recovery and metadata retry.')


if __name__=='__main__':main()
