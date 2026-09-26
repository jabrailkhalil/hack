"""Predeclared fixed paired behavioural probes; no dataset access or fitting."""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import foundation as f
import runtime
import numpy as np

SPEC=dict(dt_s=.05,duration_s=35.,initial_v_mps=4.5,initial_drive=0.,
    wheel_period_s=.1,common_noise_amplitude_mps=.01,common_noise_frequency=3.,
    load_start_s=10.,outage_end_s=15.,false_return_end_s=16.,
    ramp_start_s=10.,ramp_end_s=12.,ramp_hold_end_s=14.,
    load_amplitudes=[-.6,-.3,.3,.6],u_regular=.5,
    trajectory_schedule=[[0.,.6],[8.,0.],[12.,-.6],[20.,.1]],
    cases=['traction_coast_brake','load_-0.6','load_-0.3','load_0.3','load_0.6','false_return','ramp_-1','ramp_1'],
    veto='added false stop / new nonrecovery / RMSE > baseline + max(.05,.05*baseline)',
    score_window='trajectory full 0..35; otherwise 10..(healthy return+10)',
    note='One fixed simulator and stream; not independent truth for real recordings')


def run_case(case):
    c,r=f.profile();truth_model=f.GuardedReadoutObserver(c,readout=r)
    b=f.GuardedReadoutObserver(f.Config(**asdict(c)),readout=r)
    a=runtime.candidate_class()(f.Config(**asdict(c)),readout=r)
    tv,ta=SPEC['initial_v_mps'],0.;target=[];out={'baseline':[],'candidate':[]};u=.5
    wheel=None;previous_t=None;reference_s=0.
    for i in range(701):
        t=i*.05;d=0.
        if case=='traction_coast_brake':u=next(v for start,v in reversed(SPEC['trajectory_schedule']) if t>=start)
        if case.startswith('load_') and t>=10.:d=float(case.split('_')[1])
        if i:
            old=tv;tv,ta,_=f.predict(truth_model,tv,ta,d,u,.05);reference_s+=(old+tv)*.5*.05
        target.append((t,tv,reference_s))
        missing=(case.startswith('load_') or case=='false_return') and 10.<=t<15.
        if i%2==0:
            z=tv+(.01*math.sin(t*3.) if abs(tv)>.07 else 0.)
            if case=='false_return' and 15.<=t<16.:z+=2.
            if case.startswith('ramp_') and 10.<=t<14.:
                z+=int(case.split('_')[1])*min(3.,(t-10.)*1.5)
            wheel=f.Sample(t,z)
        wheels=(None,None) if missing else (wheel,wheel)
        cmd=f.Sample(t,u)
        for name,o in (('baseline',b),('candidate',a)):
            e=o.step(t,cmd,*wheels)
            out[name].append((t,e.v,e.s,e.mode=='STOPPED',o.drive_a,o.disturbance))
    target=np.asarray(target);mask=np.ones(len(target),bool)
    healthy=0. if case=='traction_coast_brake' else (16. if case=='false_return' else 14. if case.startswith('ramp_') else 15.)
    if case!='traction_coast_brake':mask=(target[:,0]>=10.)&(target[:,0]<healthy+10.)
    scores={}
    for name,rows in out.items():
        rows=np.asarray(rows);error=rows[:,1]-target[:,1]
        recmask=(target[:,0]>=healthy)&(target[:,0]<healthy+10.)&(abs(error)<.25)
        hits=np.flatnonzero(np.convolve(recmask.astype(int),np.ones(20,int),mode='valid')==20)
        scores[name]=dict(rmse=float(np.sqrt(np.mean(error[mask]**2))),max_error=float(np.max(abs(error[mask]))),
            false_stops=int(np.sum(mask&(target[:,1]>1.)&(rows[:,3]>0))),
            recovery_s=float(target[hits[0],0]-healthy) if len(hits) else None,
            terminal_distance_error_m=float(rows[-1,2]-rows[0,2]-target[-1,2]))
    x,y=scores['baseline'],scores['candidate'];veto=[]
    if y['false_stops']>x['false_stops']:veto.append('added_false_stop')
    if x['recovery_s'] is not None and y['recovery_s'] is None:veto.append('new_unrecovered')
    if y['rmse']>x['rmse']+max(.05,.05*x['rmse']):veto.append('rmse_regression')
    return dict(case=case,**scores,veto=veto)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    result=dict(spec=SPEC,cases=[run_case(case) for case in SPEC['cases']])
    result['passed']=not any(x['veto'] for x in result['cases'])
    f.ev.save(a.output,result);print(json.dumps(result,indent=2))
