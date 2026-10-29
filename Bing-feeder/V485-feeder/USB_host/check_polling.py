#!/usr/bin/env python3
"""A lost telemetry reply must not bury known hardware among absent IDs."""
import copy
import threading
import time

import host_service as host
from simulated_bus import SimulatedBus


def main():
    stock=host.Stock(':memory:');port=SimulatedBus()
    port.nodes[13]=copy.deepcopy(port.nodes[2]);port.nodes.pop(2)
    service=host.Feeders(port,stock,range(1,31),reply_timeout=.003)
    service.read_details(1);service.read_details(13)
    identities=lambda:sum(body.startswith('IDENT ') for _,body in port.frames)
    first=identities()
    service.observe(1);service.observe(1);assert identities()==first,'Repeated identity on routine status polls'
    port.nodes[1]['token']=(0,0);service.observe(1)
    assert identities()==first+1,'Reboot did not refresh identity'
    stock.failed(1,'Disconnected');service.observe(1)
    assert identities()==first+2,'Reconnect did not refresh identity'
    port.fail_diag=True;assert service.observe_safely(13) is None;port.fail_diag=False
    for address in range(2,31):
        if address!=13:service.observe_safely(address)
    assert not next(f for f in service.snapshot()['feeders'] if f['address']==13)['online']
    service.set_maintenance(True)
    initial_seen=next(f['seen'] for f in stock.rows() if f['address']==1)
    stopped=threading.Event();worker=threading.Thread(target=service.poll,args=(stopped,.005),daemon=True)
    worker.start()
    try:
        deadline=time.monotonic()+16
        while not next(f for f in service.snapshot()['feeders'] if f['address']==13)['online']:
            assert time.monotonic()<deadline,'Known feeder trapped in absent-ID scan'
            time.sleep(.01)
        with service.bus:
            port.fail_diag=True;service.observe_safely(13);port.fail_diag=False
        deadline=time.monotonic()+16
        while not next(f for f in service.snapshot()['feeders'] if f['address']==13)['online']:
            assert time.monotonic()<deadline,'Transient loss did not recover promptly'
            time.sleep(.01)
        deadline=time.monotonic()+16
        while next(f['seen'] for f in stock.rows() if f['address']==1)<=initial_seen:
            assert time.monotonic()<deadline,'Pause incorrectly stopped heartbeat polling'
            time.sleep(.01)
        # Several remembered but unplugged units must not starve live heartbeats.
        with service.bus:
            for address in range(20,26):
                stock.observe(address,f'{address:024X}','0000000000000001',0,(1<<29)|(1<<26)|1)
                service.observe_safely(address)
            seen=next(f['seen'] for f in stock.rows() if f['address']==1)
        deadline=time.monotonic()+16
        while next(f['seen'] for f in stock.rows() if f['address']==1)<=seen:
            assert time.monotonic()<deadline,'Unplugged known feeders starved live heartbeat'
            time.sleep(.01)
        # Routine heartbeat polls must not re-read image/configuration metadata.
        def details():return sum(body.startswith(('INFO','CONFIG ')) for _,body in port.frames)
        with service.bus:baseline=details()
        time.sleep(.7)
        with service.bus:assert details()==baseline,'Routine heartbeat re-read firmware/settings'
        # Reconnecting with the SAME boot token still refreshes firmware once.
        with service.bus:
            service.ids=[1]
            node=port.nodes.pop(1)
        deadline=time.monotonic()+2
        while not next(f['error'] for f in stock.rows() if f['address']==1):
            assert time.monotonic()<deadline;time.sleep(.01)
        with service.bus:port.nodes[1]=node;baseline=details()
        deadline=time.monotonic()+4
        while details()==baseline:
            assert time.monotonic()<deadline,'Reconnect did not refresh firmware';time.sleep(.01)
        assert service.maintenance and port.feeds==0
        assert not any(body.startswith(('FEED ','JOG ','SETCONFIG ','SETCOUNT ','BOOT ','BEGIN ')) for _,body in port.frames)
    finally:
        stopped.set();worker.join(2);stock.close()
    # Six remembered offline IDs previously starved a never-seen plugged-in unit.
    stock=host.Stock(':memory:');port=SimulatedBus()
    port.nodes[14]=copy.deepcopy(port.nodes[1]);port.nodes[14]['uid']=(14,14,14)
    service=host.Feeders(port,stock,[1,*range(8,15)],reply_timeout=.003)
    service.read_details(1)
    for address in range(8,14):
        stock.observe(address,f'{address:024X}','0000000000000001',0,(1<<29)|(1<<26)|1)
        stock.failed(address,'Disconnected')
    stopped=threading.Event();worker=threading.Thread(target=service.poll,args=(stopped,.002),daemon=True);worker.start()
    try:
        deadline=time.monotonic()+5
        while not any(r['address']==14 for r in stock.rows()):
            assert time.monotonic()<deadline,'Remembered offline IDs starved new feeder discovery';time.sleep(.01)
    finally:stopped.set();worker.join(2);stock.close()
    print('Polling checks passed: known-feeder recovery after dropped DIAG replies with 28 absent IDs; no movement/settings writes.')


if __name__=='__main__':main()
