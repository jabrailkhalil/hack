"""Non-intervening train-only activation probe. Not an accuracy candidate."""
import argparse, collections, hashlib
from concurrent.futures import ProcessPoolExecutor
from common import *

class Probe(GuardedReadoutObserver):
    def __init__(self,c):
        super().__init__(c,readout=profile()[1]);self.reference=baseline(c)
        self.stats=collections.Counter();self.deltas=[];self.time_s=0.
    def step(self,t,command=None,front=None,rear=None):
        old_t,old_v,init=self.t,self.v,self.initialized
        dt=0 if old_t is None else t-old_t
        if init and dt>0 and self._valid(command,t,self.c.command_timeout_s) and 0<command.value<=1.000001:
            q,f,cap,a,b=targets(self.c,min(command.value,1.),old_v)
            self.stats['positive_traction_ticks']+=1
            if 0<q<1 and cap<f:
                self.stats['power_limited_partial_ticks']+=1
                self.deltas.append(b-a)
                if abs(b-a)>.02:
                    self.stats['qualifying_ticks']+=1;self.time_s+=dt
        e=super().step(t,command,front,rear);ref=self.reference.step(t,command,front,rear)
        assert e==ref
        for k,v in vars(self.reference).items():
            assert v==getattr(self,k),k
        return e

def worker(args):
    bag,out=args;store=Store(out/'access'/f'{bag}.json');events,refs=store.load(bag,'train')
    assert not any(refs.values());instances=[]
    def factory(c):
        x=Probe(c);instances.append(x);return x
    a,runtime=replay(events,factory);x=instances[-1]
    row=dict(bag=bag,group=store.records[bag]['group'],outputs=len(a),stats=dict(x.stats),
        qualifying_seconds=x.time_s,mean_delta_mps2=float(np.mean(x.deltas)) if x.deltas else None,
        p95_delta_mps2=float(np.percentile(x.deltas,95)) if x.deltas else None,
        max_delta_mps2=max(x.deltas,default=None),runtime=runtime,canonical_exact=True,
        output_sha256=hashlib.sha256(a.tobytes()).hexdigest())
    save(out/'bags'/f'{bag}.json',row);print('TRAIN',bag,row['stats'],flush=True);return row

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=2);a=p.parse_args()
    if not 1<=a.workers<=8:raise ValueError('workers')
    a.output.mkdir(parents=True,exist_ok=False);save(a.output/'started.json',pins());store=Store()
    with ProcessPoolExecutor(a.workers) as pool:
        rows=list(pool.map(worker,[(b,a.output) for b in store.plan['splits']['train']]))
    groups=collections.defaultdict(lambda:dict(ticks=0,seconds=0.,bags=0))
    for r in rows:
        g=groups[r['group']];g['ticks']+=r['stats'].get('qualifying_ticks',0);g['seconds']+=r['qualifying_seconds'];g['bags']+=1
    total=sum(g['ticks'] for g in groups.values());duration=sum(g['seconds'] for g in groups.values())
    qualifying=[g for g,v in groups.items() if v['ticks']>=20 and v['seconds']>=1-1e-8]
    passed=total>=200 and duration>=10-1e-8 and len(qualifying)>=3
    result=dict(hypothesis='R4-H37',baseline_sha=BASELINE,source_status='VERIFIED',
        data_status='AVAILABLE',candidate_implemented=False,accuracy_contract_evaluated=False,
        coverage_passed=passed,coverage_status='SUFFICIENT' if passed else 'INSUFFICIENT',
        scientific_verdict='FOUNDATION_SUFFICIENT_FOR_PATCH' if passed else 'INCONCLUSIVE',
        qualifying_ticks=total,qualifying_seconds=duration,qualifying_groups=qualifying,groups=dict(groups),
        train_bags=len(rows),rows=rows,validation_opened=False,test_opened=False,
        qualification='Canonical-state proxy, not independent acceleration truth or an accuracy result')
    save(a.output/'SUMMARY.json',result);print('FOUNDATION',passed,total,duration,len(qualifying),flush=True)
if __name__=='__main__':main()
