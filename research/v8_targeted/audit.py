"""Read saved development results; apply fixed gates, reveal groups and regressions."""
import argparse
import csv
import importlib.util
import json
import math
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('targeted_audit_eval',HERE/'evaluate.py')
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)


def audit(primary, supplemental, candidate, output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    rows=[json.loads(p.read_text()) for p in sorted((Path(primary)/'bags').glob('*.json'))]
    if len(rows)!=17:raise ValueError('Expected all 17 development results')
    cr=[r['clean'] for r in rows];sr=[s for r in rows for s in r['stress']];fr=[s for r in rows for s in r['full']]
    supplements=json.loads((Path(supplemental)/'raw.json').read_text())
    summary=json.loads((Path(primary)/'summary.json').read_text())
    sup_summary=json.loads((Path(supplemental)/'summary.json').read_text())
    reasons=[];regressions=[];groups=[];all_cases=[]
    if summary['baseline_fingerprint']!='EXACT_PASS':reasons.append('baseline_fingerprint')
    for scope in ('all','30618'):
        bs=summary['scopes'][scope]['main'];cs=summary['scopes'][scope][candidate]
        if cs['fault_rmse']>bs['fault_rmse']*.95+1e-12:reasons.append(scope+':insufficient_fault_gain')
        for key,tol in [('clean_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01),('full_faulted_distance_rmse',.01)]:
            if cs[key]>bs[key]*(1+tol)+1e-12:reasons.append(scope+':aggregate:'+key)
        for suite,ms in sup_summary[scope].items():
            b=ms['models']['main'];c=ms['models'][candidate]
            if c['event_rmse'] is None or b['event_rmse'] is None:reasons.append(scope+':missing:'+suite)
            elif c['event_rmse']>b['event_rmse']*1.005+1e-12:reasons.append(scope+':supplemental:'+suite)
    for suite,items in [('clean',cr),('original',sr),('full',fr),*supplements.items()]:
        for r in items:
            rt0=r['runtime']['main'];rt1=r['runtime'][candidate]
            if rt1['causal_errors'] or rt1['resets']:reasons.append(suite+':runtime:'+r['bag'])
            for receiver,ms in r['receivers'].items():
                b,c=ms['main'],ms[candidate];case=f"{suite}:{r['bag']}:{receiver}:{r.get('fault',{}).get('kind','')}:{r.get('fault',{}).get('start','')}"
                if b['n']!=c['n'] or b['coverage']!=c['coverage']:reasons.append('coverage:'+case)
                if c['false_stop_samples']>b['false_stop_samples']:reasons.append('false_stop:'+case)
                if b.get('event_rmse') is not None and b.get('recovery_s') is not None and c.get('recovery_s') is None:reasons.append('new_unrecovered:'+case)
                if suite=='clean' and b['rmse'] is not None and c['rmse']>b['rmse']+max(.005,.05*b['rmse'])+1e-12:reasons.append('clean_per_bag:'+case)
                for key in ['rmse','event_rmse','mae','p95','bias','recovery_s','distance']:
                    x,y=e.v6.metric_value(b,key),e.v6.metric_value(c,key)
                    item=dict(suite=suite,bag=r['bag'],group=r['group'],receiver=receiver,
                        kind=r.get('fault',{}).get('kind'),duration=None if 'fault' not in r else r['fault']['end']-r['fault']['start'],
                        metric=key,baseline=x,candidate=y,delta=None if x is None or y is None else y-x)
                    all_cases.append(item)
                    if x is not None and y is not None and ((abs(y)>abs(x)) if key=='bias' else (y>x)):regressions.append(item)
    for scope in ('all','30618','30639'):
        filt=lambda x:scope=='all' or x['bag'].startswith(scope+'_')
        clean=list(filter(filt,cr));stress=list(filter(filt,sr));full=list(filter(filt,fr))
        group_ids=sorted({r['group'] for r in clean})
        for group in group_ids:
            a=[r for r in stress if r['group']==group]
            b=e.v6.macro(a,'main','event_rmse');c=e.v6.macro(a,candidate,'event_rmse')
            groups.append(dict(scope=scope,kind='per_group',group=group,baseline=b,candidate=c,error_change_percent=None if not b or c is None else 100*(c/b-1)))
            a=[r for r in stress if r['group']!=group]
            b=e.v6.macro(a,'main','event_rmse');c=e.v6.macro(a,candidate,'event_rmse')
            groups.append(dict(scope=scope,kind='leave_one_group_out',group=group,baseline=b,candidate=c,error_change_percent=None if not b or c is None else 100*(c/b-1)))
    # Distinct DB sensitivity uses only metadata; primary historical memberships unchanged.
    seen=set();dedup=[]
    for r in rows:
        h=r['clean']['db_sha256']
        if h in seen:continue
        seen.add(h);dedup.append(r)
    sensitivity=e.summarize(dedup,['main',candidate],True)
    # Independently check raw full-output integrals and preserve residual displacement.
    retained=[];max_integral_error=0.;array_files=0;identities=0
    for row in rows:
        bag=row['clean']['bag'];cl=e.np.load(Path(primary)/'arrays'/f'{bag}-clean.npz',allow_pickle=False)
        for index,r in enumerate(row['full']):
            fl=e.np.load(Path(primary)/'arrays'/f'{bag}-fault-{index}.npz',allow_pickle=False);array_files+=1
            f=r['fault']
            for name in ('main',candidate):
                a=fl[name];c=cl[name];before=a[:,0]<f['start']
                if not e.np.array_equal(a[before,:3],c[before,:3]):raise AssertionError('Prefault change')
                dv=a[:,1]-c[:,1];ds=a[:,2]-c[:,2];dt=e.np.diff(a[:,0])
                integ=e.np.r_[0.,e.np.cumsum(.5*(dv[1:]+dv[:-1])*dt)]
                err=float(e.np.max(e.np.abs(ds-ds[0]-integ)))
                max_integral_error=max(max_integral_error,err);identities+=1
                j=e.np.searchsorted(a[:,0],f['end']+10.,side='right')-1
                retained.append(dict(bag=bag,model=name,kind=f['kind'],duration=f['end']-f['start'],
                    post10_delta_s_m=float(ds[j]) if j>=0 and a[-1,0]>=f['end']+10. else None,
                    terminal_delta_s_m=float(ds[-1]),integral_error=err))
            fl.close()
        cl.close()
    if max_integral_error>1e-7:reasons.append('integral_identity')
    result=dict(status='DEVELOPMENT_PASS' if not reasons else 'DEVELOPMENT_REJECTED',candidate=candidate,
        scope='adaptive selection on reused development; not independent validation/test',
        ready_to_merge=False,reasons=sorted(set(reasons)),primary=summary['scopes'],supplemental=sup_summary,
        raw_bags=17,distinct_DBs=len(seen),original_scenarios=len(sr),full_scenarios=len(fr),
        supplemental_scenarios={k:len(v) for k,v in supplements.items()},
        integral_identities=identities,integral_max_error=max_integral_error,
        distinct_DB_sensitivity=sensitivity,groups=groups,
        original_case_counts={s:{change:sum((v['delta']<0 if change=='improved' else v['delta']>0 if change=='regressed' else v['delta']==0) for v in all_cases if v['metric']=='event_rmse' and v['suite']=='original' and v['delta'] is not None and (s=='all' or v['bag'].startswith(s+'_'))) for change in ('improved','regressed','equal')} for s in ['all','30618','30639']})
    e.save(output/'AUDIT.json',result)
    for file,items in [('all_cases.csv',all_cases),('regressions.csv',regressions),('group_sensitivity.csv',groups),('retained_displacement.csv',retained)]:
        with (output/file).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
    print(json.dumps({k:result[k] for k in ['status','reasons','original_case_counts','integral_max_error']},indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--primary',required=True);p.add_argument('--supplemental',required=True)
    p.add_argument('--candidate',default='disturbance_070');p.add_argument('--output',required=True);a=p.parse_args()
    audit(a.primary,a.supplemental,a.candidate,a.output)
