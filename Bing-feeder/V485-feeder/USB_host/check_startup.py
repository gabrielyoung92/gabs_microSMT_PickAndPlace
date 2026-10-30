#!/usr/bin/env python3
"""Startup hello expedites a normal poll without claiming device state."""
import threading
import time

import host_service as host
from simulated_bus import SimulatedBus


def main():
    stock=host.Stock(':memory:');port=SimulatedBus()
    service=host.Feeders(port,stock,[1,2],reply_timeout=.003)
    hello=host.packet(2,'ONLINE 00000002 00000485 00000022')
    for invalid in (hello[:-3]+b'00\n',hello[:-1],host.packet(2,'ONLINE 00000002'),
                    host.packet(99,'ONLINE 00000001 00000002 00000003')):
        service.startup_packet(invalid)
    assert not service.startup_ids and not stock.rows()
    # A hello interleaved with another ID's reply must not consume that reply.
    port.rx.append(hello)
    service.observe(1)
    assert service.startup_ids=={2}
    assert [row['address'] for row in stock.rows()]==[1]
    # An idle-bus hello is read before selecting the next request.
    service.startup_ids.clear();port.frames.clear();port.rx.append(hello)
    stopped=threading.Event()
    worker=threading.Thread(target=service.poll,args=(stopped,.002),daemon=True)
    worker.start()
    try:
        deadline=time.monotonic()+1
        while not any(row['address']==2 for row in stock.rows()):
            assert time.monotonic()<deadline,'Hello did not trigger discovery'
            time.sleep(.005)
    finally:stopped.set();worker.join(1)
    assert port.frames[0][0]==2 and port.frames[0][1].startswith('DIAG ')
    assert port.feeds==0
    assert not any(body.startswith(('FEED ','JOG ','SET','BOOT','BEGIN')) for _,body in port.frames)
    stock.close()
    print('Startup hello passed: CRC/shape guards, idle and interleaved reception, priority poll, no motion/settings writes.')


if __name__=='__main__':main()
