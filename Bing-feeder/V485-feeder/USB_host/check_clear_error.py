#!/usr/bin/env python3
"""Clear-error checks with simulated feeders; no hardware or real inventory."""
import copy
import http.client
import json
import threading
import host_service as host
from simulated_bus import SimulatedBus


def rejected(call):
    try:call()
    except (host.ServiceError,host.UpdateError,ValueError):return
    raise AssertionError('Expected rejection')


def main():
    port=SimulatedBus();stock=host.Stock(':memory:')
    service=host.Feeders(port,stock,[1,2],reply_timeout=.005)
    uid=service.observe(1);stock.load(uid,'Keep reel',123,2,10)
    args=dict(address=1,uid=uid)
    rejected(lambda:service.clear_error(dict(args,uid='F'*24)))
    for fault in (1,2,4):
        port.nodes[1]['fault']=fault;service.observe(1)
        before=copy.deepcopy(port.nodes[1]);baseline=stock.rows()[0]
        assert service.clear_error(args)['cleared'] and service.maintenance
        assert port.nodes[1]==dict(before,fault=0),'Clear modified runtime token, counter or configuration'
        row=next(r for r in stock.rows() if r['uid']==uid)
        assert row['loaded']==123 and row['used_pulses']==baseline['used_pulses'] and row['fault_code']==0
    port.nodes[1]['manual_running']=True;rejected(lambda:service.clear_error(args));port.nodes[1]['manual_running']=False
    port.nodes[1]['invalid_settings']=True;port.nodes[1]['fault']=3
    rejected(lambda:service.clear_error(args));assert port.nodes[1]['fault']==3
    port.nodes[1]['invalid_settings']=False;port.nodes[1]['no_clear']=True
    before=sum(body.startswith('CLEAR ') for _,body in port.frames)
    rejected(lambda:service.clear_error(args))
    assert sum(body.startswith('CLEAR ') for _,body in port.frames)==before+1,'Clear retried automatically'
    port.nodes[1]['no_clear']=False
    service.updating=True;rejected(lambda:service.clear_error(args));service.updating=False
    server=host.WebServer(0,service,demo=True)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        c.request('POST','/api/clear-error',json.dumps(args),{'Content-Type':'application/json'})
        r=c.getresponse();data=json.loads(r.read());assert r.status==200,data;assert data['cleared'];c.close()
        assert port.feeds==0
        assert not any(body.startswith(('FEED ','JOG ','BOOT','SETCONFIG ','SETCOUNT ','SETID ')) for _,body in port.frames)
    finally:server.shutdown();server.server_close();worker.join(2);stock.close()
    print('Clear error passed: single addressed request, UID/busy/settings guards, fault readback, retained configuration/token/stock, HTTP and no feed/reboot/settings writes.')


if __name__=='__main__':main()
