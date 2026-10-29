"""Read-only remaining-job stock check for powered feeders."""
from collections import Counter
import math
import time


def job_stock(job, status):
    natives=job.get('feeders',[]);rows=[]
    bus_counts=Counter(f['bus_id'] for f in natives if f.get('powered') and f.get('enabled'))
    for part in job.get('parts',[]):
        required=part['remaining']
        if not required:continue
        matching=[f for f in natives if f.get('part_id')==part['part_id'] and f.get('enabled')]
        powered=[f for f in matching if f.get('powered')]
        other=any(not f.get('powered') for f in matching)
        available=0;unknown=False;uncertain=False;notes=[];used=set();names=[]
        for native in powered:
            names.append(native['name'])
            if bus_counts[native['bus_id']]!=1:notes.append('Duplicate feeder bus ID');continue
            found=[f for f in status['feeders'] if f.get('known') and f.get('address')==native['bus_id']]
            if len(found)!=1:notes.append('Feeder not detected');continue
            feeder=found[0]
            if feeder['uid'] in used:continue
            used.add(feeder['uid'])
            if not feeder.get('online') or feeder.get('fault_code') or feeder.get('mode')!='normal':notes.append('Feeder offline or faulted');continue
            desired=feeder.get('part_assignment')
            if desired and (desired.get('status')!='synced' or desired.get('part_id')!=part['part_id']):notes.append('Part assignment not synced');continue
            if feeder.get('remaining') is None:unknown=True;continue
            available+=max(0,math.floor(feeder['remaining']));uncertain|=bool(feeder.get('uncertain'))
            if feeder.get('age_seconds',0)>status['stale_after_seconds']:notes.append('Telemetry is stale')
        if not part['part_id']:result='Missing part'
        elif not matching:result='No enabled feeder'
        elif notes:result='Check feeder'
        elif uncertain:result='Stock uncertain'
        elif available>=required:result='Stock sufficient'
        elif other:result='Untracked stock'
        elif unknown:result='Unknown stock'
        else:result='Short'
        rows.append(dict(part_id=part['part_id'],name=part.get('name',''),required=required,available=available,
                         shortage=max(0,required-available) if not unknown and not other else None,
                         feeders=names,other_feeder=other,status=result,notes=sorted(set(notes))))
    return dict(name=job.get('name',''),rows=rows,checked_at=time.time())
