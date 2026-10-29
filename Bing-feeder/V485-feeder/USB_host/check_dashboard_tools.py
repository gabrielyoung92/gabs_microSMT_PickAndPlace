#!/usr/bin/env python3
"""Remaining-job stock and removed-feature checks; no hardware or real profile."""
import copy,json,http.client,threading
import host_service as host
from dashboard_tools import job_stock
from simulated_bus import SimulatedBus


def main():
 stock=host.Stock(':memory:');port=SimulatedBus();service=host.Feeders(port,stock,[1,2],reply_timeout=.005);uid=service.observe(1);stock.load(uid,'Original reel',100,2,10)
 stock.save_details(uid,'part_assignment',dict(part_id='P1',status='synced',feeder_id='F1'))
 job=dict(name='Fixture',boards=1,total=10,remaining=5,state='Stopped',parts=[dict(part_id='P1',name='Resistor',total=10,remaining=5)],feeders=[dict(id='F1',name='Feeder1',part_id='P1',enabled=True,powered=True,bus_id=1)])
 status=service.snapshot();assert job_stock(job,status)['rows'][0]['status']=='Stock sufficient';assert job_stock(job,status)['rows'][0]['required']==5
 bad=copy.deepcopy(status);bad['feeders'][0]['remaining']=2;assert job_stock(job,bad)['rows'][0]['shortage']==3
 bad['feeders'][0]['remaining']=None;assert job_stock(job,bad)['rows'][0]['status']=='Unknown stock'
 bad=copy.deepcopy(status);bad['feeders'][0]['uncertain']=True;assert job_stock(job,bad)['rows'][0]['status']=='Stock uncertain'
 bad=copy.deepcopy(status);bad['feeders'][0]['online']=False;assert job_stock(job,bad)['rows'][0]['status']=='Check feeder'
 bad=copy.deepcopy(status);bad['feeders'][0]['part_assignment']['status']='pending';assert job_stock(job,bad)['rows'][0]['status']=='Check feeder'
 other=copy.deepcopy(job);other['feeders'][0]['powered']=False;assert job_stock(other,status)['rows'][0]['status']=='Untracked stock'
 duplicate=copy.deepcopy(job);duplicate['feeders']*=2;assert job_stock(duplicate,status)['rows'][0]['status']=='Check feeder'
 bad=copy.deepcopy(status);bad['maintenance']=True;assert job_stock(job,bad)['rows'][0]['status']=='Stock sufficient'
 done=copy.deepcopy(job);done['parts'][0]['remaining']=0;assert not job_stock(done,status)['rows']
 old=host.openpnp_request;host.openpnp_request=lambda *a,**k:copy.deepcopy(job)
 web=host.WebServer(0,service);thread=threading.Thread(target=web.serve_forever,daemon=True);thread.start()
 def request(method,path,body=None):
  c=http.client.HTTPConnection('127.0.0.1',web.server_port,timeout=5)
  c.request(method,path,None if body is None else json.dumps(body),{'Content-Type':'application/json'})
  response=c.getresponse();result=response.status,response.read();c.close();return result
 try:
  code,data=request('GET','/api/job');assert code==200
  assert json.loads(data)['rows'][0]['required']==5
  assert request('GET','/job')[0]==200
  for path in ('/nozzles','/backups','/api/backups','/api/backups/old.zip'):assert request('GET',path)[0]==404
  for path in ('/api/backup','/api/restore','/api/restore-preview'):assert request('POST',path,{})[0]==404
  for action in ('job_start','edit_nozzle','edit_nozzle_tip','configure_tip','create_nozzle_tip','configure_tip_holders','save_for_backup'):
   assert request('POST','/api/openpnp',dict(action=action))[0]==400
  assert port.feeds==0 and not any(body.startswith(('FEED ','BOOT ','SETCONFIG ','SETCOUNT ')) for _,body in port.frames)
 finally:web.shutdown();web.server_close();thread.join(2);stock.close();host.openpnp_request=old
 print('Job stock checks passed: remaining requirements, shortages, uncertain/unknown/untracked stock, offline and duplicate IDs; removed backup/nozzle routes reject requests; no hardware writes.')

if __name__=='__main__':main()
