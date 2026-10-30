#!/usr/bin/env python3
"""Bench UI/API actions against a simulated feeder; no hardware or saved inventory."""
import http.client
import json
import threading
import host_service as host
from simulated_bus import SimulatedBus


def rejected(call):
    try:call()
    except (host.ServiceError,host.UpdateError,ValueError,TimeoutError):return
    raise AssertionError('Expected rejection')


def main():
    port=SimulatedBus();stock=host.Stock(':memory:');service=host.Feeders(port,stock,[1],reply_timeout=.01,poll_interval=.001)
    uid=service.observe(1);args=dict(address=1,uid=uid)
    row=service.snapshot()['feeders'][0];assert row['diagnostics']['reset_cause']=='Power-on'
    before=sum(body.startswith(('HEALTH ','FAULTINFO ')) for _,body in port.frames)
    service.observe(1);service.observe(1)
    assert sum(body.startswith(('HEALTH ','FAULTINFO ')) for _,body in port.frames)==before,'Diagnostics repeated on routine heartbeat'
    port.nodes[1].update(fault=1,fault_target=2,fault_received=1,fault_duration=10000)
    service.observe(1);diag=service.snapshot()['feeders'][0]['diagnostics']
    assert diag['fault_code']==1 and diag['target']==2 and diag['received']==1 and diag['duration_ms']==10000
    service.clear_error(args);assert service.snapshot()['feeders'][0]['diagnostics']['fault_code']==0
    service.load_stock(1,'Reel',10,4,2,expected_uid=uid)
    rejected(lambda:service.bench_action(dict(args,action='forward')))
    rejected(lambda:service.bench_action(dict(args,uid='F'*24,action='start')))
    assert service.bench_action(dict(args,action='start'))['loading'] and service.maintenance
    assert stock.rows()[0]['mode']=='load'
    rejected(lambda:service.set_maintenance(False))
    rejected(lambda:service.feed(1,0))
    for action in ('forward','reverse'):
        assert service.bench_action(dict(args,action=action))['moved']==action
        service.read_details(1);row=stock.rows()[0];assert row['remaining']==10 and row['advances']==0
    port.nodes[1]['contact_closed']=True
    assert service.bench_action(dict(args,action='peel'))['peeling']
    assert not service.bench_action(dict(args,action='stop'))['peeling']
    assert not service.bench_action(dict(args,action='end'))['loading']
    assert service.maintenance and stock.rows()[0]['mode']=='normal'
    assert service.bench_action(args,locate=True)['locating']
    service.updating=True;rejected(lambda:service.bench_action(args,locate=True));service.updating=False
    # Missing acknowledgement never repeats a loading movement.
    service.bench_action(dict(args,action='start'));port.lose_accept=True
    before=sum(body.startswith('JOG ') for _,body in port.frames)
    service.bench_action(dict(args,action='forward'))
    assert sum(body.startswith('JOG ') for _,body in port.frames)==before+1
    service.bench_action(dict(args,action='end'))
    port.nodes[1].update(token=(0,0),reset_flags=1<<29);service.observe(1)
    assert service.snapshot()['feeders'][0]['diagnostics']['reset_cause']=='Watchdog'
    # Zero flags must stay unknown: the installed bootloader clears reset flags.
    port.nodes[1].update(token=(0,0),reset_flags=0);service.observe(1)
    assert service.snapshot()['feeders'][0]['diagnostics']['reset_cause']=='Unavailable (bootloader clears reset flags)'
    web=host.WebServer(0,service,demo=True);thread=threading.Thread(target=web.serve_forever,daemon=True);thread.start()
    try:
        c=http.client.HTTPConnection(*web.server_address,timeout=3)
        for path,body in [('/api/loading',dict(args,action='start')),('/api/loading',dict(args,action='forward')),('/api/loading',dict(args,action='end')),('/api/locate',args)]:
            c.request('POST',path,json.dumps(body),{'Content-Type':'application/json'})
            response=c.getresponse();value=json.loads(response.read());assert response.status==200,value
        c.close()
    finally:web.shutdown();web.server_close();thread.join(2);stock.close()
    print('Bench tools passed: fault snapshots, reboot cause, routine poll traffic, loading/jog stock preservation, pause/UID guards, lost ACK without replay, locate and HTTP.')


if __name__=='__main__':main()
