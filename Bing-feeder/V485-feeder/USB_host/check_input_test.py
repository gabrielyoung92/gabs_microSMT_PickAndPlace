#!/usr/bin/env python3
"""Input-test API checks with a simulated bus and temporary inventory; no hardware."""
import http.client
import json
import threading
from host_service import Feeders, Stock, WebServer, ServiceError
from simulated_bus import SimulatedBus


def rejected(call):
    try:call()
    except (ServiceError,ValueError):return
    raise AssertionError('Expected rejection')


def main():
    port=SimulatedBus();stock=Stock(':memory:');feeders=Feeders(port,stock,[1,2],reply_timeout=.01)
    uid=feeders.observe(1);args=dict(address=1,uid=uid,action='start')
    rejected(lambda:feeders.test_inputs(args))
    assert not any(body.startswith('TEST ') for _,body in port.frames)
    feeders.set_maintenance(True)
    rejected(lambda:feeders.test_inputs(dict(args,uid='F'*24)))
    port.nodes[1]['old_firmware']=True
    rejected(lambda:feeders.test_inputs(args))
    assert not any(body.startswith('TEST ') for _,body in port.frames)
    port.nodes[1]['old_firmware']=False
    port.nodes[1]['manual_running']=True
    rejected(lambda:feeders.test_inputs(args));port.nodes[1]['manual_running']=False
    result=feeders.test_inputs(args)
    assert result['active'] and not result['index_running'] and not result['peel_running']
    assert next(r for r in stock.rows() if r['uid']==uid)['mode']=='test'
    rejected(lambda:feeders.set_maintenance(False))
    # Reads and repeated Start never implicitly end/reset an existing test.
    commands=sum(body.startswith('TEST ') for _,body in port.frames)
    port.nodes[1].update(contact_closed=True,switch_changes=2)
    result=feeders.test_inputs(dict(args,action='read'))
    assert result['contact_closed'] and result['peel_requested'] and result['switch_changes']==2
    feeders.test_inputs(args)
    assert sum(body.startswith('TEST ') for _,body in port.frames)==commands
    # Host restart leaves MCU inhibition intact, discoverable through DIAG/read.
    other=Feeders(port,stock,[1,2],reply_timeout=.01);other.observe(1)
    rejected(lambda:other.set_maintenance(False));other.set_maintenance(True)
    web=WebServer(0,other,demo=True)
    thread=threading.Thread(target=web.serve_forever,daemon=True);thread.start()
    connection=http.client.HTTPConnection(*web.server_address,timeout=3)
    def post(body):
        connection.request('POST','/api/test',json.dumps(body),{'Content-Type':'application/json'})
        response=connection.getresponse();return response.status,json.loads(response.read())
    status,result=post(dict(args,action='read'));assert status==200 and result['active']
    status,result=post(dict(args,action='end'));assert status==200 and not result['active']
    other.set_maintenance(False)
    assert not any(body.startswith(('FEED ','JOG ','BOOT','BEGIN ','DATA ','SETCONFIG ','SETCOUNT ')) for _,body in port.frames)
    connection.close();web.shutdown();web.server_close();stock.close()
    print('Input test guards, old firmware, retained inhibition, live input reads and HTTP endpoint passed')


if __name__=='__main__':main()
