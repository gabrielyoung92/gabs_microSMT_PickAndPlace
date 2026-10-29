#!/usr/bin/env python3
"""Bulk firmware queue checks using only simulated devices and a fake uploader."""
import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time

import host_service as host
from bundle_firmware import package,read_bundle
from check_host import sample_image,expect_error
from simulated_bus import SimulatedBus


def main():
    with tempfile.TemporaryDirectory() as directory:
        image=sample_image();path=Path(directory)/'firmware.bin';path.write_bytes(image)
        bundle=path.with_suffix('.json');package(path,bundle);metadata,_=read_bundle(bundle)
        old_bundle=host.BUNDLE;host.BUNDLE=bundle
        stock=host.Stock(':memory:');port=SimulatedBus()
        for address in range(1,6):
            port.nodes[address]=copy.deepcopy(port.nodes[1]);port.nodes[address]['uid']=(address,address,address)
        port.nodes[4].update(image_crc=int(metadata['crc32'],16),image_size=len(image))
        service=host.Feeders(port,stock,range(1,6),reply_timeout=.005)
        for address in range(1,6):service.read_details(address)
        port.nodes.pop(5);service.observe_safely(5)
        calls=[];fail_at=None;allow_upload=threading.Event()
        def fake_update(address,data):
            assert data==image and service.maintenance and service.batch_update['active']
            expect_error(lambda:service.set_maintenance(False))
            assert next(t for t in service.snapshot()['batch_update']['items'] if t['address']==address)['stage']=='updating'
            calls.append(address)
            assert allow_upload.wait(2),'POST did not return while the upload was running'
            if address==fail_at:raise TimeoutError('Simulated upload failure')
            port.nodes[address].update(image_crc=int(metadata['crc32'],16),image_size=len(data))
            service.read_details(address)
        service.update=fake_update
        server=host.WebServer(0,service,demo=True);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def request(sha,address=None):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
            c.request('POST','/api/update-all-bundled' if address is None else '/api/update-bundled',json.dumps(dict(sha256=sha,address=address)),{'Content-Type':'application/json'})
            r=c.getresponse();value=r.status,json.loads(r.read());c.close();return value
        def finished():
            deadline=time.monotonic()+3
            while service.batch_update['active']:
                assert time.monotonic()<deadline,'Queue did not finish'
                time.sleep(.01)
        try:
            assert request(metadata['sha256'])[0]==409 and not calls
            server.demo=False
            assert request('stale-build')[0]==409 and not calls
            assert request(metadata['sha256'])[0]==200
            assert service.batch_update['active'], 'Request waited for the whole queue'
            allow_upload.set();finished()
            assert calls==[1,2,3]  # Current4 and offline5 skipped.
            assert [item['stage'] for item in service.batch_update['items']]==['complete']*3
            assert service.maintenance and not service.batch_update['active']
            # A failed unit must not block the rest; retries are explicit.
            for address in (1,2,3):
                port.nodes[address].update(image_crc=0x12345678,image_size=1024);service.read_details(address)
            calls.clear();fail_at=2
            service.queue_update(image);finished()
            assert 'Simulated upload failure' in service.batch_update['error']
            assert calls==[1,2,3]
            assert [item['stage'] for item in service.batch_update['items']]==['complete','failed','complete']
            assert not service.batch_update['active'] and service.maintenance
            snapshot=service.snapshot();snapshot['batch_update']['items'][0]['stage']='changed'
            assert service.batch_update['items'][0]['stage']=='complete'
            # Retry one feeder through the same nonblocking HTTP queue.
            calls.clear();fail_at=None;allow_upload.clear()
            assert request(metadata['sha256'],2)[0]==200
            assert service.batch_update['active']
            expect_error(lambda:service.queue_update(image,1))
            allow_upload.set();finished()
            assert calls==[2] and service.batch_update['items'][0]['stage']=='complete'
            # A current single unit is checked without reflashing it.
            calls.clear();assert request(metadata['sha256'],2)[0]==200;finished()
            assert not calls and service.batch_update['items'][0]['stage']=='current'
            # Changed hardware identity stops before the uploader.
            port.nodes[1].update(image_crc=0x12345678,image_size=1024);service.read_details(1)

            calls.clear();original=service.read_firmware
            def replacement(address,uid=None):
                port.nodes[address]['uid']=(99,99,99);port.nodes[address]['token']=(0,0);return original(address,uid)
            service.read_firmware=replacement
            service.queue_update(image);finished();assert not calls
            assert 'identity changed' in service.batch_update['error']
            assert port.feeds==0 and not any(body.startswith(('FEED ','JOG ','BOOT ','BEGIN ','SETCONFIG ','SETCOUNT ')) for _,body in port.frames)
        finally:
            server.shutdown();server.server_close();worker.join(2);stock.close();host.BUNDLE=old_bundle
    print('Bulk checks passed: ordered queue, current/offline skips, pinned build, demo rejection, pause retention, single/bulk shared queue, continue after failure and explicit single retry and changed-UID rejection; no flashing.')


if __name__=='__main__':main()
