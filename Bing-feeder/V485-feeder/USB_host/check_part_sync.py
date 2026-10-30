#!/usr/bin/env python3
"""Reel part synchronization with simulated feeders and a fake OpenPnP server."""
import http.client,json,threading,tempfile,sqlite3
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import host_service as host
from simulated_bus import SimulatedBus

class Companion(BaseHTTPRequestHandler):
    parts=[dict(id='P1',name='Resistor',package_id='PKG1',height_mm=1.0),dict(id='P2',name='Capacitor',package_id='PKG1',height_mm=2.0)]
    packages=[dict(id='PKG1',description='Test package',pad_count=2,body_width_mm=2,body_length_mm=1)]
    nozzles=[dict(id='N1',name='N1',head_id='H1',head_name='H1',nozzle_tip_ids=['T1'],loaded_tip_id='T1')]
    nozzle_tips=[dict(id='T1',name='Small'),dict(id='T2',name='Large')]
    calls=[];feeders=[dict(id='OP1',bus_id=1,part_id='P1')];blocked=False
    def log_message(self,*args):pass
    def reply(self,code,value):
        data=json.dumps(value).encode();self.send_response(code);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):self.reply(200,dict(online=True,api_version=1,nozzles=self.nozzles,nozzle_tips=self.nozzle_tips,parts=self.parts,packages=self.packages,feeders=self.feeders))
    def do_POST(self):
        args=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.calls.append(args)
        if self.blocked:self.reply(409,dict(error='OpenPnP job is running'));return
        if args['action']=='create_package':
            source=next((p for p in self.packages if p['id']==args.get('copy_from')),dict(pad_count=0,body_width_mm=0,body_length_mm=0))
            package=dict(source,id=args['package_id'],description=args.get('description',''));self.packages.append(package)
            self.reply(200,dict(saved=True,package=package));return
        if args['action']=='edit_package':
            package=next(p for p in self.packages if p['id']==args['package_id']);assert package==args['expected']
            package.update(description=args['description'],nozzle_tip_ids=args['nozzle_tip_ids'])
            self.reply(200,dict(saved=True,package=package));return
        if args['action']=='create_part':
            part=dict(id=args['part_id'],name=args.get('name',''),package_id=args['package_id'],height_mm=args['height_mm']);self.parts.append(part)
            self.reply(200,dict(saved=True,part=part));return
        if args['action']=='edit_part':
            part=next(p for p in self.parts if p['id']==args['part_id'])
            assert part==args['expected']
            part.update(name=args['name'],package_id=args['package_id'],height_mm=args['height_mm'])
            self.reply(200,dict(saved=True,part=part));return
        assert args['bus_id']==1
        if args['action']=='add_feeder':
            assert not self.feeders
            self.feeders.append(dict(id='OP1',bus_id=1,part_id=args['part_id']))
            self.reply(200,dict(saved=True,feeder=self.feeders[0]));return
        assert args['action']=='set_feeder_part' and args['feeder_id']=='OP1'
        self.feeders[0]['part_id']=args['part_id'];self.reply(200,dict(saved=True,feeder=self.feeders[0]))

def main():
    directory=tempfile.TemporaryDirectory();database=Path(directory.name)/'stock.sqlite3'
    # Exercise upgrading the previous metadata schema as well as persistence.
    db=sqlite3.connect(database);db.execute('CREATE TABLE device_details(uid TEXT PRIMARY KEY,firmware TEXT,configuration TEXT)');db.close()
    stock=host.Stock(database);port=SimulatedBus();port.nodes[1]['default']=2;service=host.Feeders(port,stock,[1],reply_timeout=.005);service.observe(1)
    uid=stock.rows()[0]['uid'];companion=ThreadingHTTPServer(('127.0.0.1',0),Companion)
    old=host.OPENPNP_URL;host.OPENPNP_URL='http://127.0.0.1:'+str(companion.server_port)
    web=host.WebServer(0,service);threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (companion,web)]
    for thread in threads:thread.start()
    def post(path,args):
        c=http.client.HTTPConnection('127.0.0.1',web.server_port,timeout=3);c.request('POST',path,json.dumps(args),{'Content-Type':'application/json'});r=c.getresponse();result=r.status,json.loads(r.read());c.close();return result
    try:
        args=dict(address=1,uid=uid,label='Reel A',part_id='P2',quantity=100,part_spacing_mm=4)
        code,result=post('/api/stock',args);assert code==200 and result['part_assignment']['status']=='synced'
        assert Companion.feeders[0]['part_id']=='P2' and stock.rows()[0]['label']=='Reel A'
        Companion.blocked=True
        code,result=post('/api/stock',dict(args,part_id='P1'));assert code==200 and result['part_assignment']['status']=='pending'
        port.completed(1);service.observe(1);assert stock.rows()[0]['remaining']==99
        Companion.blocked=False
        code,result=post('/api/part-sync',dict(uid=uid));assert code==200 and result['part_assignment']['status']=='synced'
        assert stock.rows()[0]['remaining']==99 and stock.rows()[0]['used_pulses']==2
        assert Companion.feeders[0]['part_id']=='P1'
        code,result=post('/api/stock',dict(args,part_id=''));assert code==200 and Companion.feeders[0]['part_id']==''
        # A missing matching feeder is created once, then reused on retry.
        Companion.feeders=[]
        code,result=post('/api/stock',dict(args,part_id='P2'))
        assert code==200 and result['part_assignment']['status']=='synced'
        assert len(Companion.feeders)==1 and Companion.calls[-1]['action']=='add_feeder'
        created=sum(call['action']=='add_feeder' for call in Companion.calls)
        post('/api/part-sync',dict(uid=uid))
        assert sum(call['action']=='add_feeder' for call in Companion.calls)==created
        # Duplicate powered feeders never cause an arbitrary assignment.
        saved=list(Companion.feeders);before=len(Companion.calls)
        for matches in (saved+saved,):
            Companion.feeders=matches
            assert service.sync_part(uid)['status']=='pending'
            assert len(Companion.calls)==before
        Companion.feeders=saved
        before=stock.rows()[0]['loaded']
        assert post('/api/stock',dict(args,uid='F'*24,quantity=999))[0]==409
        assert stock.rows()[0]['loaded']==before
        web.demo=True;before=len(Companion.calls)
        assert post('/api/stock',args)[0]==409 and post('/api/part-sync',dict(uid=uid))[0]==409
        assert len(Companion.calls)==before
        web.demo=False
        edit=dict(action='edit_part',part_id='P1',name='Edited',package_id='PKG1',height_mm=1.5,expected=dict(Companion.parts[0]))
        assert post('/api/openpnp',edit)[0]==200 and Companion.parts[0]['height_mm']==1.5
        assert post('/api/openpnp',dict(action='edit_package',package_id='PKG1',expected=dict(Companion.packages[0]),description='Edited package',nozzle_tip_ids=[]))[0]==200
        for route in ('/','/parts','/packages','/job','/firmware','/settings'):
            c=http.client.HTTPConnection('127.0.0.1',web.server_port);c.request('GET',route);response=c.getresponse();assert response.status==200 and b'<!doctype html>' in response.read();c.close()
        assert post('/api/openpnp',dict(action='create_package',package_id='NEWPKG',description='New',copy_from='PKG1'))[0]==200
        assert post('/api/openpnp',dict(action='create_part',part_id='NEWPART',name='New',package_id='NEWPKG',height_mm=1))[0]==200
        assert Companion.parts[-1]['package_id']=='NEWPKG'
        for action in ('edit_nozzle','edit_nozzle_tip','configure_tip','create_nozzle_tip','configure_tip_holders'):
            before=len(Companion.calls)
            assert post('/api/openpnp',dict(action=action))[0]==400
            assert len(Companion.calls)==before
        assert port.feeds==0 and not any(body.startswith(('FEED ','JOG ','BOOT ','SETCONFIG ','SETCOUNT ')) for _,body in port.frames)
    finally:
        for s in (web,companion):s.shutdown();s.server_close()
        for thread in threads:thread.join(2)
        stock.close();host.OPENPNP_URL=old
    reopened=host.Stock(database)
    assert reopened.rows()[0]['part_assignment']['part_id']=='P2'
    reopened.close();directory.cleanup()
    print('Part sync checks passed: matching feeder, clear assignment, pending/busy, retry without stock reset, missing/duplicate/changed identity and demo isolation.')

if __name__=='__main__':main()
