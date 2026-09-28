"""Baseline-only foundation: hypothetical per-step drive endpoint, no feedback."""
import argparse, math
from pathlib import Path
from collections import Counter
from support import *

def decay(d,target,dt,tau):return d+(1-math.exp(-dt/tau))*(target-d)

def segments(old,t,prior,received):
    # Only already received events; never sort the bag. Equal-value refreshes
    # keep one segment, preserving constant-command arithmetic.
    current=prior;start=old;result=[];changed=[]
    for s in sorted((x for x in received if old<x.t<=t),key=lambda x:x.t):
        if s.value!=current.value:
            if s.t>start:result.append((s.t-start,current.value))
            changed.append(s.t);start=s.t;current=s
    if t>start:result.append((t-start,current.value))
    return result,changed

class Probe(GuardedReadoutObserver):
    def reset(self,**kw):
        super().reset(**kw);self.arrivals=[];self.prior=None;self.rows=[];self.counters=Counter()
    def step(self,t,command=None,front=None,rear=None):
        old=self.t
        if old is not None:
            ready=[s for s in self.arrivals if s.t<=t]
            late=[s for s in ready if s.t<=old]
            self.counters['late_received_commands']+=len(late)
            valid=lambda s:self._valid(s,t,self.c.command_timeout_s) and abs(s.value)<=1.000001
            if self.prior is not None and valid(self.prior) and valid(command):
                prior=max(late,key=lambda x:x.t) if late and max(s.t for s in late)>self.prior.t else self.prior
                seg,changed=segments(old,t,prior,ready)
                if changed:
                    d=self.drive_a
                    for dt,u in seg:d=decay(d,self.drive_target(u,self.v),dt,self.c.actuator_tau_s)
                    b=decay(self.drive_a,self.drive_target(command.value,self.v),t-old,self.c.actuator_tau_s)
                    interior=[s for s in changed if old+1e-9<s<t-1e-9]
                    self.rows.append(dict(t=t,changes=len(changed),interior=len(interior),
                        phase_offsets=[(s-old)/(t-old) for s in changed],drive_delta=d-b,
                        materially_changed=bool(interior and abs(d-b)>=1e-6)))
            self.arrivals=[s for s in self.arrivals if s.t>t]
        e=super().step(t,command,front,rear);self.prior=command;return e

class InputTrace(Timeline):
    def ingest(self,ch,s):
        ok=super().ingest(ch,s)
        if ok and ch==0:self.observer.arrivals.append(s)
        return ok

def run(output):
    output.mkdir(parents=True,exist_ok=False);save(output/'started.json',provenance())
    store=Store(output/'access.json');rows=[];total=0
    for bag in store.plan['splits']['train']:
        events,refs=store.load(bag,'train');assert not any(refs.values())
        c,r=profile();o=Probe(c,readout=r);tl=InputTrace(o,20.,0.);ticks=0;causal=0
        for t,ch,value in events:
            tl.ingest(int(ch),Sample(float(t),float(value)))
            for e,held in tl.advance():
                ticks+=1;causal+=sum(s is not None and s.t>e.t+1e-9 for s in held)
        group=store.records[bag]['group'];count=sum(x['materially_changed'] for x in o.rows)
        row=dict(bag=bag,group=group,outputs=ticks,input_events=len(events),
            changed_steps=len(o.rows),material_steps=count,causal_errors=causal,resets=tl.resets,
            counters=dict(o.counters),changes=o.rows)
        save(output/'bags'/(bag+'.json'),row);rows.append(row);total+=ticks
        print('FOUNDATION',bag,count,flush=True)
    groups=Counter()
    for row in rows:groups[row['group']]+=row['material_steps']
    offsets=[v for row in rows for x in row['changes'] for v in x['phase_offsets']]
    delta=[abs(x['drive_delta']) for row in rows for x in row['changes']]
    quant=lambda v:dict(zip(['min','p50','p95','max'],map(float,np.quantile(v,[0,.5,.95,1])))) if v else None
    count=sum(groups.values());ng=sum(n>=10 for n in groups.values())
    result=dict(stage='foundation_train_only',candidate_implemented=False,
        train_bags=len(rows),source_groups=len(groups),outputs=total,material_steps=count,
        group_counts=dict(groups),eligible_groups=ng,phase_fraction=quant(offsets),abs_drive_delta_mps2=quant(delta),
        coverage_threshold=dict(material_steps=100,groups_with_10_steps=3,drive_delta_mps2=1e-6),
        coverage_passed=count>=100 and ng>=3,causal_errors=sum(x['causal_errors'] for x in rows),
        test_opened=False,validation_opened=False,
        limitation='Hypothetical endpoint on baseline pre-state, not a candidate accuracy measurement; source stamp need not be physical actuation time')
    save(output/'SUMMARY.json',result);print(result,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);run(p.parse_args().output)
