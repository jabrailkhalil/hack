"""Re-run canonical v8 and assert passive probe parity on original development.

No H38 observer is enabled. Both names required by the old scorer are v8.
Results are baseline fingerprints, NOT candidate improvements.
"""
import argparse
import csv
from dataclasses import asdict
import datetime
import importlib.util
import inspect
import json
from pathlib import Path
import time
from foundation import Probe
from support import ROOT, ev, np, RoleStore, profile, Config, ReadoutConfig, GuardedReadoutObserver, OPS, save, sha, BASELINE, TREE


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

v6=module('h38_pinned_v6',ROOT/'tools/research_v6/compare.py')
guarded=module('h38_pinned_guarded',ROOT/'tools/research_guarded/compare.py')


class CheckedProbe(Probe):
    """Check ALL original fields after every step against independent v8."""
    def __init__(self,c,readout):
        self.reference=GuardedReadoutObserver(c,readout=readout)
        self.checked_steps=0
        super().__init__(c,readout=readout)
    def reset(self,**kw):
        super().reset(**kw)
        if hasattr(self,'reference'):self.reference.reset(**kw)
    def step(self,*a,**kw):
        e=super().step(*a,**kw);ref=self.reference.step(*a,**kw)
        if e!=ref:raise AssertionError('Probe changed returned Estimate')
        for k,v in vars(self.reference).items():
            if v!=getattr(self,k):raise AssertionError('Probe changed baseline field '+k)
        self.checked_steps+=1
        return e


def run(root,output):
    output.mkdir(parents=True,exist_ok=False)
    cfg,rd=profile();store=RoleStore(root);started=time.perf_counter()
    provenance=dict(baseline_sha=BASELINE,baseline_tree=TREE,config=cfg,readout=rd,operational=OPS,
      canonical_class='reserve_odometry.guarded_readout.GuardedReadoutObserver',canonical_module=inspect.getfile(GuardedReadoutObserver),
      diagnostic_class='CheckedProbe',diagnostic_module=str(Path(__file__).resolve()),
      labels=dict(baseline_v2='canonical_v8',balanced_physics='passive_probe_over_canonical_v8'),
      candidate_implemented=False,accuracy_contract_evaluated=False,validation_opened=False,test_opened=False,
      created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
      protected_sha256=ev.protected_files(),diagnostic_sha256={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')})
    save(output/'started.json',provenance)
    clean=[];stress=[];parity=[]
    for bag in store.plan['splits']['development']:
        events,refs=store.load(bag,'development');group=store.records[bag]['group']
        models={'baseline_v2':Config(**cfg),'balanced_physics':Config(**cfg)}
        current_probe=None
        def factory(c):
            nonlocal current_probe
            if c is models['baseline_v2']:return GuardedReadoutObserver(c,readout=ReadoutConfig(**rd))
            current_probe=CheckedProbe(c,readout=ReadoutConfig(**rd));return current_probe
        original_factory,original_replay=ev.Observer,ev.replay
        arrays=[]
        def replay(*a,**kw):
            result=original_replay(*a,**kw);arrays.append(result);return result
        ev.Observer=factory;ev.replay=replay
        def compare(window,fault=None):
            arrays.clear()
            result=ev.score(window,refs,models,OPS,fault)
            assert len(arrays)==2
            a,ainfo=arrays[0];b,binfo=arrays[1]
            if not np.array_equal(a,b,equal_nan=True) or ainfo!=binfo:raise AssertionError('Probe output/runtime differs')
            parity.append(dict(bag=bag,fault=fault,outputs=len(a),checked_steps=current_probe.checked_steps,
              all_original_fields_equal=True,all_returned_estimates_equal=True,arrays_equal=True,
              runtime_equal=True,output_sha256=__import__('hashlib').sha256(a.tobytes()).hexdigest()))
            return dict(bag=bag,group=group,**result)
        try:
            c=compare(events);clean.append(c);faults=[]
            for fault,window in guarded.fault_windows(events):
                item=compare(window,fault);item['fault']=fault;stress.append(item);faults.append(item)
        finally:ev.Observer=original_factory;ev.replay=original_replay
        save(output/'bags'/(bag+'.json'),dict(clean=c,stress=faults))
        save(output/'access.json',store.access)
        print('BASELINE_AUDIT',bag,c['outputs'],len(faults),flush=True)
    summary=v6.summary(clean,stress,'baseline_v2')
    expected=dict(clean_rmse=.09266814298282507,fault_rmse=.2375486120563008,pooled_rmse=.1293056944774334,distance_rmse=5.310295004801444,samples=394221)
    errors={k:summary[k]-v for k,v in expected.items()}
    assert summary['samples']==expected['samples'] and max(abs(v) for v in errors.values())<1e-10,('Baseline mismatch',errors)
    result=dict(**provenance,summary=summary,expected_fingerprint=expected,fingerprint_absolute_deltas=errors,
      fingerprint_verified=True,clean=clean,stress=stress,parity=parity,clean_bags=len(clean),original_fault_scenarios=len(stress),
      all_original_state_comparisons=sum(x['checked_steps'] for x in parity),elapsed_s=time.perf_counter()-started)
    save(output/'results.json',result)
    rows=[]
    for phase,items in [('clean',clean),('fault',stress)]:
        for row in items:
            for receiver,scores in row['receivers'].items():
                m=scores['baseline_v2'];f=row.get('fault',{})
                rows.append(dict(bag=row['bag'],group=row['group'],phase=phase,receiver=receiver,kind=f.get('kind','clean'),
                  fault_start=f.get('start'),fault_end=f.get('end'),n=m['n'],coverage=m['coverage'],rmse=m['rmse'],
                  mae=m.get('mae'),bias=m.get('bias'),p95=m.get('p95'),event_rmse=m.get('event_rmse'),
                  recovery_s=m.get('recovery_s'),false_stop_samples=m.get('false_stop_samples'),
                  distance_rmse=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m')))
    with (output/'per_bag_receiver_fault.csv').open('w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    save(output/'SUMMARY.json',{k:v for k,v in result.items() if k not in ('clean','stress','parity','protected_sha256')})
    print(json.dumps(dict(summary=summary,parity_cases=len(parity),checked_steps=result['all_original_state_comparisons'],deltas=errors),indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.data_root,a.output)
