#!/usr/bin/env python3
"""Feeder-owned stock survives absent host, feeder reboot and lost SQL cache."""
import host_service as host
from simulated_bus import SimulatedBus
from check_host import expect_error


def main():
    port=SimulatedBus();stock=host.Stock(':memory:')
    s=host.Feeders(port,stock,[1],reply_timeout=.005,poll_interval=.001)
    uid=s.observe(1);s.read_details(1,uid)
    row=lambda:stock.rows()[0]
    assert row()['stock_source']=='feeder' and row()['remaining'] is None and row()['advances']==0
    port.completed(1,3);s.observe(1)
    assert row()['remaining'] is None and row()['advances']==3
    s.load_stock(1,'Reel',20,pitch=4)
    assert row()['remaining']==20 and row()['advances']==0
    # The host can be completely absent during these completed feeds.
    stock.close();port.completed(1,3)
    port.nodes[1]['token']=(0,0);port.nodes[1]['counter']=0 # Reboot with saved stock retained.
    stock=host.Stock(':memory:');s=host.Feeders(port,stock,[1],reply_timeout=.005,poll_interval=.001)
    s.read_details(1)
    assert row()['remaining']==17 and row()['advances']==3 and not row()['uncertain']
    # Deliberately wrong SQLite inventory must not override the device.
    stock.db.execute('UPDATE feeders SET loaded=9999,used_pulses=0');stock.db.commit()
    assert row()['remaining']==17
    s.load_stock(1,'Renamed',pitch=4)
    assert row()['remaining']==17 and row()['advances']==3
    before=sum(body.startswith('SETSTOCK ') for _,body in port.frames)
    port.nodes[1]['lose_stock_ack']=True
    s.load_stock(1,'New reel',10,pitch=4)
    assert row()['remaining']==10 and row()['advances']==0
    assert sum(body.startswith('SETSTOCK ') for _,body in port.frames)==before+1
    port.nodes[1]['lose_stock_ack']=False
    assert s.feed(1,0).startswith('ok ')
    assert row()['remaining']==9 and row()['advances']==1
    port.nodes[1]['advances']=0xFFFFFFFF;port.nodes[1]['remaining']=None
    assert s.feed(1,0).startswith('ok ')
    assert row()['remaining'] is None and row()['advances']==0xFFFFFFFF
    s.load_stock(1,'Empty reel',0,pitch=4)
    assert s.feed(1,0).startswith('ok ') and row()['remaining']==0 and row()['advances']==1
    expect_error(lambda:s.load_stock(1,'Too many',65535,pitch=4))
    port.nodes[1]['stock_supported']=False
    expect_error(lambda:s.load_stock(1,'Unsupported',5,pitch=4))
    stock.close()
    print('Feeder stock passed: unset quantity, absent host, reboot, deleted/wrong SQL, metadata-only edits, lost ACK without replay, feed counts, zero and saturation.')


if __name__=='__main__':main()
