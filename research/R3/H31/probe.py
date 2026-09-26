"""R3-H31 premise probe/export; baseline only, no ensemble, no validation/test IO."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys
from collections import Counter
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools/finalization'),str(ROOT/'src/reserve_odometry')]
import evaluate as ev
import numpy as np
from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.timeline import Timeline
BASE='e3b0c9c039d2953fbfcda51231263d38ef9f1024'

def profile():
    p={}
    for line in (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text().splitlines():
        key,sep,value=line.strip().partition(':')
        if sep and key.startswith(('model.','readout.')):p[key]=float(value)
    c=Config(**{k[6:]:v for k,v in p.items() if k.startswith('model.')})
    r=ReadoutConfig(**{k[8:]:v for k,v in p.items() if k.startswith('readout.')})
    assert c.common_mode_quarantine_s==1.5 and c.wheel_time_compensation==0
    assert c.adaptation_tau_s==.5 and r.gain==1 and r.holdoff_s==.5
    return c,r

def load(store,bag,role):
    if role=='train':return store.load(bag,'train')
    if role!='development' or store.records[bag]['split']!=role:
        raise PermissionError('Only original train/development allowed')
    row=store.records[bag];path=store.root/bag/(bag+'_0.db3')
    if ev.sha(path)!=row['sha256']:raise ValueError('Bag hash mismatch')
    allowed=list(ev.ex.CHANNELS)+list(ev.ex.REFS)
    store.access.append(dict(bag=bag,purpose=role,topics=allowed,sha256=row['sha256']))
    events=[];refs={'master':[],'rover':[]}
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
        sql=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
             'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
        for topic,typ,raw in con.execute(sql,allowed):
            stamp,values=ev.decode(raw,typ);t=(stamp-row['sensor_start_ns'])/1e9
            if topic in ev.ex.CHANNELS:
                ch=ev.ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
            else:
                speed=math.hypot(float(values[0]),float(values[1]))
                if math.isfinite(speed):refs[ev.ex.REFS[topic]].append((t,speed))
    return np.asarray(events,float),refs

def regime(command,c):
    return 1 if command.value>c.command_deadband else (-1 if command.value<-c.command_deadband else 0)

def premise(events):
    c,r=profile();o=GuardedReadoutObserver(c,readout=r);tl=Timeline(o,rate_hz=20,delay_s=0)
    pending=None;next_launch=-math.inf;old=None;last_stamps=(-math.inf,-math.inf)
    counts=Counter();errors=[];prev_outage=False
    for t,ch,value in events:
        tl.ingest(int(ch),Sample(float(t),float(value)))
        for e,held in tl.advance():
            counts['outputs']+=1;cmd,f,rear=held
            healthy=(not e.command_stale and f is not None and rear is not None
                     and o._valid(f,e.t,c.max_age_s) and o._valid(rear,e.t,c.max_age_s)
                     and abs(f.t-rear.t)<=.05 and abs(f.value-rear.value)<=.15
                     and all(x in ('ACCEPTED','DUPLICATE_OR_OLD') for x in (e.front_status,e.rear_status))
                     and abs(e.v)>.5 and e.mode not in ('WAITING_FOR_INITIALIZATION','INITIALIZED','STOPPED','REACQUIRING'))
            outage=e.mode=='MODEL_ONLY' and not healthy
            counts['potential_outage_outputs']+=outage
            counts['natural_outage_episodes']+=outage and not prev_outage;prev_outage=outage
            reg=regime(cmd,c) if not e.command_stale else None
            if pending is not None:
                if not healthy or reg!=pending['reg'] or e.t>pending['end']+.25:
                    pending=None;counts['aborted_forecasts']+=1
                else:
                    p=pending
                    if e.t<=p['end']+1e-9:p['forecast']=p['shadow'].step(e.t,cmd).v
            if not healthy:old=None;continue
            if f.t<=last_stamps[0] or rear.t<=last_stamps[1]:continue
            last_stamps=(f.t,rear.t);z=(f.value+rear.value)*.5;tz=(f.t+rear.t)*.5
            if pending and old and old[0]<=pending['end']<=tz and 0<tz-old[0]<=.25:
                p=pending;weight=(p['end']-old[0])/(tz-old[0]);target=old[1]+weight*(z-old[1])
                errors.append(dict(start=p['start'],end=p['end'],scored_at=e.t,regime=p['reg'],
                                   predicted=p['forecast'],wheel_target=target,error=p['forecast']-target))
                counts['completed_forecasts']+=1;pending=None
            old=(tz,z)
            if pending is None and e.t>=next_launch:
                pending=dict(start=e.t,end=e.t+1,reg=reg,shadow=copy.deepcopy(o),forecast=e.v)
                next_launch=e.t+2;counts['launched_forecasts']+=1
    return dict(counts=dict(counts),errors=errors,causal_errors=tl.resets)

def main():
    a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True);a.add_argument('--export',action='store_true');args=a.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);store=ev.ex.Store();rows=[];manifest=[]
    for role in ('train','development'):
        for bag in store.plan['splits'][role]:
            events,refs=load(store,bag,role)
            if args.export:
                out=args.output/'streams'/role/(bag+'.npz');out.parent.mkdir(parents=True,exist_ok=True)
                np.savez_compressed(out,events=events,master=np.asarray(refs['master'],float).reshape(-1,2),rover=np.asarray(refs['rover'],float).reshape(-1,2))
                manifest.append(dict(bag=bag,role=role,group=store.records[bag]['group'],bag_sha256=store.records[bag]['sha256'],stream_sha256=ev.sha(out)))
            if role=='train':
                row=dict(bag=bag,group=store.records[bag]['group'],**premise(events));rows.append(row)
            print('PROBE_OR_TRANSPORT',role,bag,flush=True)
    ev.save(args.output/'train_premise.json',dict(baseline=BASE,horizon_s=1.,launch_spacing_s=2.,target='trusted wheel interpolation; NOT ground truth',rows=rows))
    ev.save(args.output/'stream_manifest.json',dict(baseline=BASE,split_sha256=ev.sha(ROOT/'research/split_v3.json'),records=manifest))
    ev.save(args.output/'access.json',dict(access=store.access,development_use='transport only; no candidate or GNSS scoring before PLAN',validation_opened=False,test_opened=False))
    flat=[x for row in rows for x in row['errors']];counts=Counter()
    for row in rows:counts.update(row['counts'])
    summary=dict(baseline=BASE,train_bags=len(rows),source_groups=len({row['group'] for row in rows}),counts=dict(counts),
                 completed_groups=len({row['group'] for row in rows if row['errors']}),
                 endpoint_rmse_mps=float(np.sqrt(np.mean([x['error']**2 for x in flat]))) if flat else None,
                 endpoint_abs_p95_mps=float(np.quantile([abs(x['error']) for x in flat],.95)) if flat else None,
                 beyond_03mps=sum(abs(x['error'])>.3 for x in flat),
                 by_regime={str(reg):dict(n=sum(x['regime']==reg for x in flat),rmse=float(np.sqrt(np.mean([x['error']**2 for x in flat if x['regime']==reg])))) for reg in (-1,0,1) if any(x['regime']==reg for x in flat)},
                 references_used_for_premise=False,validation_opened=False,test_opened=False)
    ev.save(args.output/'PREMISE_SUMMARY.json',summary);print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':main()
