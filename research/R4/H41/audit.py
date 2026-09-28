"""Summarize immutable H41 evidence; never loads bags or changes selection gates."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import compare as comp


def change(b,c):
    return None if b is None or c is None or b==0. else 100.*(c/b-1.)


def save_csv(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('x',newline='') as out:
        w=csv.DictWriter(out,keys);w.writeheader();w.writerows(rows)


def audit(a):
    a.output.mkdir(parents=True,exist_ok=False)
    raw=json.loads((a.input/'results.json').read_text());rows=raw['rows']
    old=json.loads((a.input/'decision.json').read_text());new=comp.gate(rows)
    if old!=new:raise AssertionError('Exact gate recomputation mismatch')
    csv_rows=[];regressions=[];groups=[];missing=[];cases={};distance=[]
    metric_keys=('rmse','event_rmse','mae','bias','p95','recovery_s','n','coverage','false_stop_samples','distance')
    for suite,items in rows.items():
        usable=0
        for row in items:
            fault=row.get('fault') or {};kind=fault.get('kind','clean')
            for receiver,ms in row['receivers'].items():
                b,c=ms[comp.BASE],ms[comp.CAND]
                if b['rmse'] is None:missing.append(dict(suite=suite,bag=row['bag'],receiver=receiver,fault=fault))
                else:usable+=1
                cr=dict(suite=suite,bag=row['bag'],group=row['group'],receiver=receiver,fault=kind,
                    start_s=fault.get('start'),end_s=fault.get('end'))
                for key in metric_keys:
                    bv,cv=comp.v6.metric_value(b,key),comp.v6.metric_value(c,key)
                    cr['baseline_'+key]=bv;cr['candidate_'+key]=cv
                    cr['delta_'+key]=cv-bv if bv is not None and cv is not None else None
                    if key not in ('bias','n','coverage','false_stop_samples'):
                        cr['change_percent_'+key]=change(bv,cv)
                    if key in ('rmse','event_rmse','mae','p95','recovery_s','distance') and bv is not None and cv is not None and cv>bv+1e-12:
                        regressions.append(dict(suite=suite,bag=row['bag'],group=row['group'],receiver=receiver,
                            fault=kind,start_s=fault.get('start'),end_s=fault.get('end'),metric=key,
                            baseline=bv,candidate=cv,delta=cv-bv,change_percent=change(bv,cv)))
                csv_rows.append(cr)
            if row.get('distance_residual'):
                distance.append(dict(bag=row['bag'],group=row['group'],fault=kind,start_s=fault['start'],end_s=fault['end'],**row['distance_residual']))
        cases[suite]=dict(bag_replays=len(items),receiver_cases_with_reference=usable,
            original_groups=len({r['group'] for r in items}),
            reference_groups=len({r['group'] for r in items if any(s[comp.BASE]['rmse'] is not None for s in r['receivers'].values())}))
        for group in sorted({r['group'] for r in items}):
            subset=[r for r in items if r['group']==group]
            g=dict(suite=suite,group=group,bag_replays=len(subset))
            for key in ('rmse','event_rmse','mae','bias','p95','recovery_s','distance'):
                b=comp.v6.macro(subset,comp.BASE,key);c=comp.v6.macro(subset,comp.CAND,key)
                g['baseline_'+key]=b;g['candidate_'+key]=c;g['change_percent_'+key]=change(b,c)
            groups.append(g)
    aggregation=[]
    for key,b in new['baseline'].items():
        c=new['candidate'][key]
        aggregation.append(dict(metric=key,baseline=b,candidate=c,delta=None if b is None or c is None else c-b,change_percent=change(b,c)))
    type_rows=[]
    for suite in ('original','low_speed','common_mode','full_faulted'):
        for kind,duration in sorted({(r['fault']['kind'],round(r['fault']['end']-r['fault']['start'],5)) for r in rows[suite]}):
            subset=[r for r in rows[suite] if r['fault']['kind']==kind and abs(r['fault']['end']-r['fault']['start']-duration)<1e-7]
            b=comp.v6.macro(subset,comp.BASE,'event_rmse');c=comp.v6.macro(subset,comp.CAND,'event_rmse')
            type_rows.append(dict(suite=suite,fault=kind,duration_s=duration,baseline_event_rmse=b,candidate_event_rmse=c,change_percent=change(b,c),
                baseline_false_stops=comp.v6.total(subset,comp.BASE,'false_stop_samples'),candidate_false_stops=comp.v6.total(subset,comp.CAND,'false_stop_samples'),
                baseline_unrecovered=comp.v6.unrecovered(subset,comp.BASE),candidate_unrecovered=comp.v6.unrecovered(subset,comp.CAND)))
    save_csv(a.output/'per_case.csv',csv_rows);save_csv(a.output/'per_group.csv',groups)
    save_csv(a.output/'aggregate.csv',aggregation);save_csv(a.output/'fault_types.csv',type_rows)
    save_csv(a.output/'regressions.csv',regressions);save_csv(a.output/'full_faulted_distance_residual.csv',distance)
    result=dict(exact_gate_recomputation=True,cases=cases,missing=missing,
        regression_count=len(regressions),distance_residual_cases=len(distance),
        max_absolute_terminal_delta_s_m=max((abs(x['delta_s_bag_end_m']) for x in distance),default=None),
        largest_event_absolute_regressions=sorted([r for r in regressions if r['metric']=='event_rmse'],key=lambda r:r['delta'],reverse=True)[:10],
        largest_clean_regressions=sorted([r for r in regressions if r['suite']=='clean' and r['metric']=='rmse'],key=lambda r:r['delta'],reverse=True)[:10],
        largest_distance_regressions=sorted([r for r in regressions if r['metric']=='distance'],key=lambda r:r['delta'],reverse=True)[:10],
        largest_recovery_regressions=sorted([r for r in regressions if r['metric']=='recovery_s'],key=lambda r:r['delta'],reverse=True)[:10],
        activation=new['coverage'],candidate_source_sha=json.loads((a.input/'started.json').read_text())['source_sha'],
        raw_results_sha256=hashlib.sha256((a.input/'results.json').read_bytes()).hexdigest(),
        NOTE='Post-hoc descriptive slicing of the single unchanged candidate; not new selection thresholds or independent trials')
    comp.ev.save(a.output/'audit.json',result)
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);audit(p.parse_args())
