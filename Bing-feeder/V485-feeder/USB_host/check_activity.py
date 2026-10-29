#!/usr/bin/env python3
"""Activity/SSE checks with simulated feeders and ephemeral loopback sockets."""
import http.client
import json
import socket
import threading
import time
import host_service as host
from check_host import expect_error
from simulated_bus import SimulatedBus


def main():
    stock=host.Stock(':memory:');port=SimulatedBus();port.feed_delay=.08
    feeders=host.Feeders(port,stock,[1],reply_timeout=.02,feed_timeout=.4,poll_interval=.005)
    feeders.observe(1);assert not feeders.activity_snapshot()['activities']
    web=host.WebServer(0,feeders,demo=True);tcp=host.GcodeServer(0,feeders)
    workers=[threading.Thread(target=server.serve_forever,daemon=True) for server in (web,tcp)]
    for worker in workers:worker.start()
    connection=http.client.HTTPConnection('127.0.0.1',web.server_port,timeout=2)
    def read_event(response):
        while True:
            line=response.readline()
            assert line,'Activity stream closed unexpectedly'
            if line.startswith(b'data: '):
                value=json.loads(line[6:]);assert response.readline()==b'\n';return value
    try:
        connection.request('GET','/api/events');response=connection.getresponse()
        assert response.status==200 and response.getheader('Content-Type')=='text/event-stream'
        assert read_event(response)['activities']==[]
        replies=[]
        def advance():
            with socket.create_connection(tcp.server_address,timeout=2) as client:
                client.sendall(b'M600 N1 F0\n');replies.append(client.recv(512))
        feeder_thread=threading.Thread(target=advance);feeder_thread.start()
        stages=[]
        while 'completed' not in stages:
            stages.extend(event['stage'] for event in read_event(response)['activities'])
        feeder_thread.join(2)
        assert replies and replies[0].startswith(b'ok') and port.feeds==1
        assert 'advancing' in stages and stages.index('advancing')<stages.index('completed'),stages
        assert feeders.activity_snapshot()['activities'][0]['label']=='Advanced'
        # Reconnection receives the current held event without any serial operation.
        before=len(port.frames)
        reconnect=http.client.HTTPConnection('127.0.0.1',web.server_port,timeout=2)
        reconnect.request('GET','/api/events');again=reconnect.getresponse()
        assert read_event(again)['activities'][0]['stage']=='completed'
        assert len(port.frames)==before
        again.close();reconnect.close()
        # Manual movement is detected from counters; no unsolicited bus writes.
        port.nodes[1]['counter']+=2;feeders.observe(1)
        assert feeders.activities[1]['stage']=='observed' and feeders.activities[1]['source']=='sensor'
        port.nodes[1]['manual_running']=True;feeders.observe(1)
        assert feeders.activities[1]['stage']=='advancing' and feeders.activities[1]['source']=='device'
        port.nodes[1]['manual_running']=False;port.nodes[1]['counter']+=1;feeders.observe(1)
        assert feeders.activities[1]['stage']=='observed' and port.feeds==1
        # MCU reset is not reported as a fresh manual movement.
        revision=feeders.activity_revision;port.nodes[1]['token']=(0,0);port.nodes[1]['counter']=0
        feeders.observe(1);assert feeders.activity_revision==revision
        port.unknown=True;expect_error(lambda:feeders.feed(1,0))
        assert feeders.activities[1]['stage']=='failed' and port.feeds==2
        assert not feeders.active_feeds
        assert not any(body.startswith(('SETCONFIG','SETCOUNT','BOOT','BEGIN')) for _,body in port.frames)
    finally:
        response.close();connection.close()
        for server in (web,tcp):server.shutdown();server.server_close()
        for worker in workers:worker.join(2)
        stock.close()
    print('Activity checks passed: live TCP/SSE phases, held completion, reconnection, manual sensor changes, reset exclusion and unconfirmed failure without replay.')


if __name__=='__main__':main()
