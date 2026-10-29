#!/usr/bin/env python3
"""Feeder list/configuration checks with temporary SQLite and a simulated bus."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import patch

import host_service as host
from bundle_firmware import package,read_bundle
from check_host import sample_image,expect_error
from simulated_bus import SimulatedBus


def main():
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);database=folder/'stock.sqlite3'
        image=folder/'firmware.bin';image.write_bytes(sample_image())
        bundle=folder/'firmware.json';package(image,bundle)
        metadata,_=read_bundle(bundle);old_bundle=host.BUNDLE;host.BUNDLE=bundle
        stock=host.Stock(database);port=SimulatedBus()
        port.nodes[1]['image_crc']=int(metadata['crc32'],16)
        service=host.Feeders(port,stock,[1,2,3],reply_timeout=.01)
        service.read_details(1);service.read_details(2)
        one=next(f for f in service.snapshot()['feeders'] if f['address']==1)
        uid=one['uid'];assert one['online'] and one['known']
        assert one['firmware_info']['version']==metadata['version']
        # A new bundled release must not erase the known version of the old image.
        with patch.object(host,'read_bundle',return_value=(dict(metadata,crc32='00000000'),b'')):
            service.read_firmware(1,uid)
        assert next(f['firmware_info']['version'] for f in stock.rows() if f['uid']==uid)==metadata['version']
        assert one['configuration']['feed_reverse'] is False
        original=port.nodes.pop(2);service.observe_safely(2);service.observe_safely(3)
        states={f['address']:f for f in service.snapshot()['feeders']}
        assert states[2]['known'] and not states[2]['online'] and states[2]['firmware_info']['crc32']=='12345678'
        assert not states[3]['known'] and not states[3]['online'] and states[3]['seen'] is None
        args=dict(address=1,uid=uid,feed_reverse=True,peel_reverse=False,switch_no=False,pitch_mm='6')
        def saves():return [body for _,body in port.frames if body.startswith(('SETCONFIG ','SETCOUNT '))]
        expect_error(lambda:service.save_configuration(args));assert not saves()
        service.set_maintenance(True)
        expect_error(lambda:service.save_configuration(dict(args,uid='0'*24)));assert not saves()
        expect_error(lambda:service.save_configuration(dict(args,pitch_mm='3')));assert not saves()
        identities=sum(body.startswith('IDENT ') for _,body in port.frames)
        service.save_configuration(args)
        assert sum(body.startswith('IDENT ') for _,body in port.frames)==identities
        assert port.nodes[1]['options']==(1,0,0) and port.nodes[1]['default']==3
        assert len(saves())==2
        # Unchanged settings never write EEPROM again.
        service.save_configuration(args);assert len(saves())==2
        assert not any(body.startswith(('FEED ','JOG ','BOOT ','BEGIN ')) for _,body in port.frames)
        # Interrupted multi-setting save: one option write, no retry, actual readback.
        original_count=host.set_count
        def failed_count(*args,**kwargs):raise TimeoutError('Simulated lost connection before count save')
        host.set_count=failed_count
        try:expect_error(lambda:service.save_configuration(dict(args,feed_reverse=False,pitch_mm='8')))
        finally:host.set_count=original_count
        assert len(saves())==3 and not port.nodes[1]['options'][0]
        current=next(f for f in service.snapshot()['feeders'] if f['uid']==uid)
        assert not current['configuration']['feed_reverse'] and current['default_count']==3
        # The real HTTP route uses the same checked save path.
        web=host.WebServer(0,service,demo=True)
        worker=threading.Thread(target=web.serve_forever,daemon=True);worker.start()
        try:
            connection=http.client.HTTPConnection('127.0.0.1',web.server_port,timeout=3)
            connection.request('POST','/api/configure',json.dumps(dict(args,feed_reverse=False)),{'Content-Type':'application/json'})
            response=connection.getresponse();assert response.status==200,response.read();response.read();connection.close()
        finally:web.shutdown();web.server_close();worker.join(2)
        # A changed MCU boot token triggers automatic metadata refresh, no writes.
        port.nodes[1]['token']=(0,0);service.observe(1)
        service.set_maintenance(False);stopped=threading.Event()
        poller=threading.Thread(target=service.poll,args=(stopped,.002),daemon=True);poller.start()
        try:
            deadline=time.monotonic()+2
            while True:
                row=next(f for f in service.snapshot()['feeders'] if f['uid']==uid)
                if row['firmware_info']['monitor_token']==row['token']:break
                assert time.monotonic()<deadline,'Automatic metadata refresh did not run'
                time.sleep(.005)
        finally:stopped.set();poller.join(2)
        assert len(saves())==3
        # Successful upload refreshes settings immediately, clearing an old
        # unsupported-CONFIG error without waiting for the ten-minute cache.
        stock.save_details(uid,'configuration',dict(error='Old firmware has no CONFIG',read_at=time.time()))
        service.set_maintenance(True)
        with patch.object(host,'upload',lambda link,image,progress:progress('complete',len(image),len(image))):
            service.update(1,sample_image())
        updated=next(f for f in service.snapshot()['feeders'] if f['uid']==uid)
        assert not updated['configuration'].get('error') and service.maintenance
        assert not service.updating and len(saves())==3
        service.set_maintenance(False)
        # Stock spacing uses physical millimetres for every supported width.
        for width,step in ((8,2),(12,4),(16,4),(24,4)):
            port.nodes[1]['width']=width
            service.load_stock(1,'Spacing test',100,part_spacing_mm=8)
            current=next(f for f in stock.rows() if f['uid']==uid)
            assert current['pitch']==8//step
            port.nodes[1]['counter']+=1;service.observe(1)
            current=next(f for f in stock.rows() if f['uid']==uid)
            assert current['remaining']==100-step/8
            expect_error(lambda:service.load_stock(1,'Invalid',999,part_spacing_mm=step+1))
            assert next(f for f in stock.rows() if f['uid']==uid)['label']=='Spacing test'
        port.nodes[1]['width']=8;service.observe(1)
        # Hardware details and offline identities survive process/database reopen.
        stock.close();stock=host.Stock(database)
        restarted=host.Feeders(SimulatedBus(),stock,[1,2,3],reply_timeout=.01)
        states={f['address']:f for f in restarted.snapshot()['feeders']}
        assert states[1]['firmware_info']['version']==metadata['version']
        assert states[1]['configuration']['feed_reverse'] is False
        assert states[2]['known'] and not states[2]['online'] and not states[3]['known']
        stock.close();host.BUNDLE=old_bundle
    print('Details checks passed: known/offline/unseen rows, persistent firmware/settings, UID/pause validation, exact pitch, no redundant writes and partial-save readback.')


if __name__=='__main__':main()
