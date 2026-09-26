"""Post-result read-only audit of the unchanged candidate's recovery distance.

No new candidate/selection: repeat full-faulted bags to sample delta_s at the
exact baseline/candidate reference-confirmed recovery defined by official score.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import compare as c


def task(args):
    bag,root=args;store=c.f.Store(Path(root));events,refs=store.load(bag,'development')
    records=[]
    for fault,_ in c.original_windows(events):
        cfg,r=c.f.profile();cand=c.f.Config(**asdict(cfg));models={c.BASE:cfg,c.CAND:cand};arrays={}
        original_factory,original_replay=c.ev.Observer,c.ev.replay
        def make(conf):return c.f.GuardedReadoutObserver(conf,readout=r) if conf is cfg else c.runtime.candidate_class()(conf,readout=r)
        def capture(ev,conf,ops,fault=None):
            arr,info=original_replay(ev,conf,ops,fault);arrays[id(conf)]=arr;return arr,info
        try:
            c.ev.Observer=make;c.ev.replay=capture
            metrics=c.ev.score(events,refs,models,c.f.OPS,fault)
        finally:c.ev.Observer=original_factory;c.ev.replay=original_replay
        b,a=arrays[id(cfg)],arrays[id(cand)]
        if not c.np.array_equal(b[:,0],a[:,0]):raise AssertionError('Changed timestamps')
        for receiver,m in metrics['receivers'].items():
            row=dict(bag=bag,group=store.records[bag]['group'],receiver=receiver,kind=fault['kind'],start_s=fault['start'],end_s=fault['end'],
                baseline_recovery_s=m[c.BASE].get('recovery_s'),candidate_recovery_s=m[c.CAND].get('recovery_s'),
                candidate_minus_baseline_s_at_bag_end_m=float(a[-1,2]-b[-1,2]),
                baseline_output_sha256=hashlib.sha256(b.tobytes()).hexdigest(),candidate_output_sha256=hashlib.sha256(a.tobytes()).hexdigest())
            for label,key in [('baseline',c.BASE),('candidate',c.CAND)]:
                recovery=m[key].get('recovery_s')
                target=None if recovery is None else fault['end']+recovery
                for suffix,delta in [('start',0.),('confirmation_end',.95)]:
                    t=None if target is None else target+delta
                    idx=None if t is None else int(c.np.argmin(abs(a[:,0]-t)))
                    if idx is not None and abs(a[idx,0]-t)>1e-8:raise AssertionError('Recovery timestamp missing')
                    row[f'{label}_recovery_{suffix}_t_s']=t
                    row[f'delta_s_at_{label}_recovery_{suffix}_m']=None if idx is None else float(a[idx,2]-b[idx,2])
            records.append(row)
    print('RECOVERY_AUDIT',bag,len(records),flush=True)
    return dict(rows=records,access=store.access)


def run(a):
    if a.output.exists():raise FileExistsError(a.output)
    a.output.mkdir(parents=True)
    c.f.check_source(a.source_receipt)
    original=json.loads(a.reference_results.read_text())['rows']['full_faulted']
    store=c.f.Store(a.data_root);rows=[];access=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        for item in pool.map(task,[(b,str(a.data_root)) for b in store.plan['splits']['development']]):rows.extend(item['rows']);access.extend(item['access'])
    checked=0;maximum=0.
    for row in rows:
        source=next(x for x in original if x['bag']==row['bag'] and x['fault']['kind']==row['kind'] and x['fault']['start']==row['start_s'] and x['fault']['end']==row['end_s'])
        m=source['receivers'][row['receiver']]
        for lhs,rhs in [(row['baseline_recovery_s'],m[c.BASE].get('recovery_s')),(row['candidate_recovery_s'],m[c.CAND].get('recovery_s')),(row['candidate_minus_baseline_s_at_bag_end_m'],source['distance_residual']['delta_s_bag_end_m'])]:
            if lhs is None or rhs is None:
                if lhs!=rhs:raise AssertionError('Missingness mismatch')
            else:
                delta=abs(lhs-rhs);maximum=max(maximum,delta);checked+=1
                if delta>1e-10:raise AssertionError('Unchanged full-bag output drifted')
    with (a.output/'confirmed_recovery_distance.csv').open('x',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    c.ev.save(a.output/'audit.json',dict(stage='post_result_diagnostic_no_retuning',
        candidate_source_sha='d1381c61e771a104eb2fc65853b60ec5c861843c',
        rows=len(rows),reproduction_fields=checked,max_absolute_reproduction_delta=maximum,
        interpretation='delta_s is candidate minus baseline, not ground truth. Recovery time is official start of a20-sample good run; confirmation_end is19 output periods later. Missing recovery remains null.',
        access=access,test_opened=False,validation_opened=False))
    print('RECOVERY_REPRODUCTION',checked,maximum,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--source-receipt',type=Path);p.add_argument('--reference-results',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
