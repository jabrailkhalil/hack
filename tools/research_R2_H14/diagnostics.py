"""Preregistered standalone synthetic checks; never admission accuracy evidence."""
from dataclasses import asdict
import argparse
import csv
import math
from pathlib import Path
from common import profile,Pristine,AsyncAdaptationObserver,save
from reserve_odometry.core import Sample,clip


def run(out):
    out.mkdir(parents=True,exist_ok=False);c,r,_=profile();summaries=[];all_rows=[]
    kinds=['healthy_sync','healthy_async','dropout_async','single_spike',
           'alternating_zeros','common_lock','startup','low_speed_lock']
    for kind in kinds:
        truth=Pristine(c,readout=r);v=0. if kind=='startup' else 1.5 if kind=='low_speed_lock' else 4.
        drive=0.;dt=.05;d_true=0. if kind=='low_speed_lock' else .12
        models={'baseline':Pristine(c,readout=r),'candidate':AsyncAdaptationObserver(c,readout=r)}
        held=[None,None];stats={n:dict(squares=0.,max_error=0.,false_stops=0,outputs=0,
                            causal_errors=0,mode_counts={}) for n in models}
        for k in range(401):
            t=k*dt
            u=0. if kind=='low_speed_lock' else .35 if t<5 else 0. if t<8 else .1 if t<13 else -.3
            if k:
                drive+=(1-math.exp(-dt/c.actuator_tau_s))*(truth.drive_target(u,v)-drive)
                next_v=v+dt*clip(drive-truth.resistance(v)+d_true,-c.max_accel_mps2,c.max_accel_mps2)
                v=0. if u<=c.command_deadband and v*next_v<0 else next_v
            for ch in range(2):
                if kind=='healthy_sync':new=(k%2==0)
                else:new=(k%2==ch)
                if not new:continue
                if kind=='dropout_async' and 8<=t<13:held[ch]=None;continue
                z=v
                if kind=='single_spike' and ch==0 and k==80:z+=5.
                if kind=='common_lock' and 6<=t<6.6:z=0.
                # Alternate which channel is zero on successive 0.1s cycles;
                # this is distinct from both held channels becoming locked.
                if kind=='alternating_zeros' and 6<=t<6.6 and ch==(k//2)%2:z=0.
                if kind=='low_speed_lock' and 1<=t<2:z=0.
                held[ch]=Sample(t,z)
            for name,o in models.items():
                e=o.step(t,Sample(t,u),*held);s=stats[name]
                if e.mode=='WAITING_FOR_INITIALIZATION':continue
                err=e.v-v;s['squares']+=err*err;s['outputs']+=1;s['max_error']=max(s['max_error'],abs(err))
                s['false_stops']+=int(v>1 and e.mode=='STOPPED')
                s['causal_errors']+=sum(x is not None and x.t>e.t+1e-9 for x in held)
                s['mode_counts'][e.mode]=s['mode_counts'].get(e.mode,0)+1
                all_rows.append([kind,name,t,v,e.v,e.s,o.disturbance,e.mode,e.front_status,e.rear_status,
                                 getattr(o,'_h14_updated',False)])
        for name,s in stats.items():
            s['rmse']=math.sqrt(s.pop('squares')/s['outputs']);s['h14_counts']=getattr(models[name],'_h14_counts',None)
        summaries.append(dict(scenario=kind,models=stats))
    safety=all(x['models']['candidate']['false_stops']<=x['models']['baseline']['false_stops'] and
               x['models']['candidate']['causal_errors']==0 for x in summaries)
    assert next(x for x in summaries if x['scenario']=='healthy_async')['models']['candidate']['h14_counts']['async_updates']>0
    save(out/'results.json',dict(scope='synthetic mechanism/safety diagnosis, NOT real-recording accuracy',
        truth_definition='fixed baseline physical coefficients + fixed external disturbance 0.12 m/s^2 (0 for low_speed_lock); causal Euler truth',
        candidate_parameters_fitted=False,safety_no_new_false_stops_or_future=safety,scenarios=summaries))
    with (out/'trace.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['scenario','model','t','truth_v','output_v','output_s','disturbance','mode',
                                   'front_status','rear_status','adaptation_update']);w.writerows(all_rows)
    if not safety:raise AssertionError('Synthetic safety regression; no validation permitted')
    return summaries

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.output)
