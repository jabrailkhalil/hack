"""R6-H57: one change to H44 training anchor selection. No runtime edits.

Stages are deliberately separate: enumerate, fit C0/C1, check after freeze.
Original H44 numerical functions are imported unchanged and hash-bound.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import csv
import sys
import time
import math
import platform
import numpy as np
from scipy.optimize import least_squares
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'research/R5/H44'))
import fit as h44
from interface import profile, effective, with_effective, BASE
from baseline_preflight import sha, write, source_integrity
PLAN_SHA = 'c846a9f65e80309dd304d16beb55eacb3679f6d3'
PHASES = ('traction', 'braking', 'coast')


def read(path):
    return json.loads(Path(path).read_text())


def csv_write(path, rows):
    rows=list(rows)
    with Path(path).open('x', newline='') as f:
        w=csv.DictWriter(f, sorted(set().union(*(r.keys() for r in rows))))
        w.writeheader(); w.writerows(rows)


def source_files():
    files=[Path(__file__)] + [ROOT/'research/R5/H44'/n for n in ('fit.py','interface.py','baseline_preflight.py')]
    return {p.relative_to(ROOT).as_posix():sha(p) for p in files}


def phase(row, cfg):
    return 'traction' if row[2]>cfg.command_deadband else 'braking' if row[2]<-cfg.command_deadband else 'coast'


def eligible_reason(w, target, cfg):
    """The exact H44 predicate, factored out without changing cutoffs or order."""
    if not np.all(np.isfinite(w)) or not np.allclose(np.diff(w[:,0]),.05,rtol=0,atol=1e-9):
        return 'missing_or_grid'
    ages=w[:,0,None]-w[:,[1,3,5]]
    if np.any(ages < -1e-9) or np.any(ages > np.array([cfg.command_timeout_s,cfg.max_age_s,cfg.max_age_s])):
        return 'stale_or_future'
    if (np.any(np.abs(w[:,2])>1.000001) or np.any(np.abs(w[:,[4,6]])>cfg.max_speed_mps)
        or np.any(np.abs(w[:,3]-w[:,5])>cfg.pair_skew_s)
        or np.any(np.abs(w[:,4]-w[:,6])>cfg.disagreement_mps)):
        return 'wheel_or_command_invalid'
    if not np.any(np.abs(w[100:,4]+w[100:,6])*.5 > .5):
        return 'no_motion'
    if not np.all(np.isfinite(target)):
        return 'teacher_missing_or_masked'
    return 'eligible'


def quantile_indices(n):
    """Nearest positions q*(n-1), exact integer arithmetic, lower tie."""
    if n < 0: raise ValueError('negative count')
    if n <= 2: return list(range(n))
    result=[]
    for numerator in (n-1, 2*(n-1)):
        quotient,remainder=divmod(numerator,3)
        result.append(quotient + int(2*remainder>3))
    # n=3 independently rounded quantiles collide. Preserve equal counts:
    # closest DISTINCT ordered pair; equal-cost tie goes to earlier pair.
    if n == 3: return [0, 1]
    assert len(set(result))==2
    return result


def select(meta, strategy):
    if strategy not in ('C0','C1'):raise ValueError('unknown strategy')
    bins=defaultdict(list)
    for i,m in enumerate(meta):
        if m['wire_representative']==m['bag']:bins[(m['bag'],m['phase'])].append(i)
    result=[]
    for key,indices in sorted(bins.items()):
        indices.sort(key=lambda i:meta[i]['anchor_s'])
        positions=list(range(min(2,len(indices)))) if strategy=='C0' else quantile_indices(len(indices))
        result.extend(indices[k] for k in positions)
    return sorted(result, key=lambda i:(meta[i]['bag'], meta[i]['anchor_s']))


def foundation(meta, c0, c1):
    bybin=lambda ids: Counter((meta[i]['bag'],meta[i]['phase']) for i in ids)
    if bybin(c0)!=bybin(c1):raise AssertionError('unfair selected counts')
    w0=h44.balanced_weights([meta[i] for i in c0]);w1=h44.balanced_weights([meta[i] for i in c1])
    # Pairing by bag/phase avoids time ordering changing the phase sequence.
    def keyed(ids,weights):
        d=defaultdict(list)
        for i,w in zip(ids,weights):d[(meta[i]['bag'],meta[i]['phase'])].append(float(w))
        return dict(d)
    if keyed(c0,w0)!=keyed(c1,w1):raise AssertionError('unfair weights')
    rows=[]
    for group in sorted({m['group'] for m in meta}):
        x=[i for i in c0 if meta[i]['group']==group];y=[i for i in c1 if meta[i]['group']==group]
        if not x:continue
        a=sorted(x,key=lambda i:(meta[i]['bag'],meta[i]['phase'],meta[i]['anchor_s']))
        b=sorted(y,key=lambda i:(meta[i]['bag'],meta[i]['phase'],meta[i]['anchor_s']))
        replaced=len(set(x)-set(y));shifts=[abs(meta[j]['anchor_s']-meta[i]['anchor_s']) for i,j in zip(a,b)]
        rows.append(dict(group=group,fold=meta[x[0]]['fold'],windows=len(x),replaced=replaced,
                         replacement_fraction=replaced/len(x),median_shift_s=float(np.median(shifts)),
                         materially_changed=replaced/len(x)>=.5 and np.median(shifts)>=10))
    counts={fold:dict(windows=sum(meta[i]['fold']==fold for i in c0),
                     groups=len({meta[i]['group'] for i in c0 if meta[i]['fold']==fold}),
                     phase_groups={p:len({meta[i]['group'] for i in c0 if meta[i]['fold']==fold and meta[i]['phase']==p}) for p in PHASES}) for fold in ('fit','check')}
    material=sum(r['fold']=='fit' and r['materially_changed'] for r in rows)
    passed=(len(c0)>=30 and material>=3 and counts['fit']['groups']>=3 and counts['check']['groups']>=2
            and all(counts['fit']['phase_groups'][p]>=3 and counts['check']['phase_groups'][p]>=2 for p in ('traction','braking')))
    return dict(passed=passed,counts=counts,material_fit_groups=material,equal_counts=True,equal_weights=True),rows


def check_lock(folder):
    j=read(folder/'SELECTION_FREEZE.json')
    if j['source_files']!=source_files():raise ValueError('Changed source after selection freeze')
    for n,h in j['files'].items():
        if sha(folder/n)!=h:raise ValueError('Changed selection/check artifact: '+n)
    return j


def enumerate_anchors(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    lock,handoff=h44.dependencies(args.lock,args.teacher)
    if lock['hypothesis_id']!='R6-H57':raise PermissionError('Wrong consumer')
    source_integrity(args.source_receipt)
    folds={x['bag']:x for x in read(lock['files']['folds']['path'])['records']}
    entries={x['bag']:x for x in handoff['files'] if x.get('kind')=='teacher_array'}
    representatives={}
    for bag in sorted(folds):representatives.setdefault(folds[bag]['wire_sha256'],bag)
    store=h44.ex.Store(args.data_root);cfg,ro,_=profile()
    write(out/'started.json',dict(stage='F0',plan_sha=PLAN_SHA,source_files=source_files(),lock_sha256=sha(args.lock),
          source_sha=args.source_sha,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),check_errors_read=False))
    meta=[]; windows=[]; targets=[]; audits=[]; total_ticks=0
    with (out/'ANCHOR_AUDIT.jsonl').open('x') as stream:
        for bag,f in sorted(folds.items()):
            if store.records[bag]['split']!='train' or entries[bag]['db_sha256']!=store.records[bag]['sha256']:
                raise PermissionError('Wrong train identity')
            events,_=store.load(bag,'train');rows,native,info=h44.capture(events);total_ticks+=len(rows)
            if info['causal_errors'] or info['resets']:raise AssertionError('Schedule failure')
            with np.load(args.teacher/entries[bag]['path'],allow_pickle=False) as z:
                q=np.rint(rows[:,0]*1e9).astype(np.int64)+store.records[bag]['sensor_start_ns']
                tg=h44.teacher_grid(z['stamp_ns'],z['speed_mps'],z['accepted'],q)
            reasons=Counter();bins=Counter();available=Counter();eligible_n=0
            for k in range(100,len(rows)-100,100):
                w=rows[k-100:k+101];y=tg[k:k+101];ph=phase(rows[k],cfg)
                third=min(2,int(3*(rows[k,0]-rows[0,0])/max(rows[-1,0]-rows[0,0],.05)))
                reason=eligible_reason(w,y,cfg);reasons[reason]+=1;bins[str(third)]+=1
                if reason in ('eligible','teacher_missing_or_masked'):available['vehicle_valid_'+str(third)]+=1
                if reason=='eligible':available['teacher_valid_'+str(third)]+=1;eligible_n+=1
                m=dict(bag=bag,group=f['group'],fold=f['fold'],phase=ph,anchor_s=float(rows[k,0]),
                       anchor_index=k,anchor_id=f'{bag}:{k}',wire_sha256=f['wire_sha256'],
                       wire_representative=representatives[f['wire_sha256']],time_third=third,
                       speed_mps=float(abs(rows[k,4]+rows[k,6])*.5),command=float(rows[k,2]),
                       eligibility_reason=reason)
                # NaN is permitted only in audit's explicitly missing descriptor; emit null.
                for name in ('speed_mps','command'):
                    if not math.isfinite(m[name]):m[name]=None
                stream.write(json.dumps(m,allow_nan=False)+'\n')
                if reason=='eligible':meta.append(m);windows.append(w.copy());targets.append(y.copy())
            audits.append(dict(bag=bag,group=f['group'],fold=f['fold'],outputs=len(rows),eligible=eligible_n,
                          representative=representatives[f['wire_sha256']],reasons=dict(reasons),
                          time_counts=dict(bins),teacher_availability=dict(available),runtime=info))
            print('F0',bag,'eligible',eligible_n,flush=True)
    c0=select(meta,'C0');c1=select(meta,'C1')
    # Exact historical control identity. No old residuals/fit metrics are used.
    oldmeta=read(args.h44_evidence/'evidence/train_windows_complete/windows.json')
    oldkeys=[(m['bag'],m['phase'],m['anchor_s']) for m in oldmeta]
    if oldkeys!=[(meta[i]['bag'],meta[i]['phase'],meta[i]['anchor_s']) for i in c0]:raise AssertionError('C0 differs from H44 selection')
    with np.load(args.h44_evidence/'evidence/train_windows_complete/windows.npz',allow_pickle=False) as z:
        if not np.array_equal(z['samples'],np.asarray([windows[i] for i in c0])):raise AssertionError('C0 samples differ')
        if not np.array_equal(z['gnss'],np.asarray([targets[i] for i in c0])):raise AssertionError('C0 targets differ')
    gate,diff=foundation(meta,c0,c1)
    check=[i for i,m in enumerate(meta) if m['fold']=='check' and m['bag']==m['wire_representative']]
    selected={'C0_FIT':[i for i in c0 if meta[i]['fold']=='fit'],
              'C1_FIT':[i for i in c1 if meta[i]['fold']=='fit'], 'CHECK_GRID':check,
              'LEGACY_CHECK':[i for i in c0 if meta[i]['fold']=='check']}
    for name,ids in selected.items():
        np.savez_compressed(out/(name+'.npz'),samples=np.asarray([windows[i] for i in ids]),gnss=np.asarray([targets[i] for i in ids]))
        write(out/(name+'.json'),[meta[i] for i in ids])
    write(out/'ELIGIBLE_ANCHORS.json',meta)
    write(out/'FIRST_TWO_ANCHORS.json',[meta[i] for i in c0]);write(out/'STRATIFIED_ANCHORS.json',[meta[i] for i in c1])
    csv_write(out/'SELECTION_DIFF.csv',diff);write(out/'BAG_COVERAGE.json',audits);write(out/'access.json',store.access)
    gate.update(total_ticks=total_ticks,eligible_anchors=len(meta),eligible_wire_representative_anchors=sum(m['bag']==m['wire_representative'] for m in meta),
                common_check_windows=len(check),C0_historical_exact=True)
    write(out/'FOUNDATION.json',gate)
    names=[p.name for p in out.iterdir() if p.is_file()]
    write(out/'SELECTION_FREEZE.json',dict(plan_sha=PLAN_SHA,source_files=source_files(),source_sha=args.source_sha,
          dependency_lock_sha256=sha(args.lock),files={n:sha(out/n) for n in sorted(names)},foundation_passed=gate['passed']))
    print('FOUNDATION',json.dumps(gate),flush=True)


def fit_variant(args):
    sf=check_lock(args.selection)
    if not sf['foundation_passed']:raise PermissionError('Foundation failed')
    if args.variant not in ('C0','C1'):raise PermissionError('Unknown variant')
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    meta=read(args.selection/(args.variant+'_FIT.json'))
    if any(m['fold']!='fit' for m in meta):raise PermissionError('Only fit arrays may train')
    with np.load(args.selection/(args.variant+'_FIT.npz'),allow_pickle=False) as z:samples=z['samples'];target=z['gnss']
    predictor=h44.Predictor(samples);prior=np.asarray(effective(predictor.config));weights=h44.balanced_weights(meta)
    previous_calls=0
    if args.variant=='C1':
        if not args.control:raise PermissionError('C1 requires completed C0 receipt')
        control=read(args.control)
        if control['selection_freeze_sha256']!=sha(args.selection/'SELECTION_FREEZE.json'):raise ValueError('Different selection freeze')
        previous_calls=control['actual_residual_calls']
    calls=[];start=time.perf_counter()
    write(out/'started.json',dict(variant=args.variant,plan_sha=PLAN_SHA,source_files=source_files(),
          selection_freeze_sha256=sha(args.selection/'SELECTION_FREEZE.json'),prior=prior.tolist(),
          check_arrays_loaded=False,previous_residual_calls=previous_calls))
    def residual(x):
        if previous_calls+len(calls)>=1000:raise RuntimeError('Residual call budget')
        pred=predictor.predict(x);ve,ie=h44.errors(pred,target,samples)
        res=np.concatenate([ve/h44.SCALES,ie/(h44.HORIZONS*h44.SCALES)],axis=1)
        res=(res*np.sqrt(weights[:,None]/6)).ravel()
        row=dict(call=len(calls)+1,total_call=previous_calls+len(calls)+1,logratio=x.tolist(),
                 data_loss=float(res@res),prior_loss=float(.01*np.mean(x*x)))
        calls.append(row)
        with (out/'residual_calls.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        if len(calls)%20==0:print('FIT',args.variant,len(calls),row['data_loss'],flush=True)
        return np.r_[res,np.sqrt(.01/3)*x]
    result=least_squares(residual,np.zeros(3),bounds=(np.log(h44.LOW/prior),np.log(h44.HIGH/prior)),
              method='trf',jac='2-point',x_scale=1.,max_nfev=80,ftol=1e-8,xtol=1e-8,gtol=1e-8)
    cfg=with_effective(predictor.config,prior*np.exp(result.x))
    output=dict(variant=args.variant,success=bool(result.success),message=result.message,nfev=int(result.nfev),njev=int(result.njev),
          actual_residual_calls=len(calls),total_residual_calls=previous_calls+len(calls),cost=float(result.cost),
          optimality=float(result.optimality),logratio=result.x.tolist(),effective=effective(cfg),config=asdict(cfg),
          readout=asdict(predictor.readout),selection_freeze_sha256=sha(args.selection/'SELECTION_FREEZE.json'),
          source_files=source_files(),check_evaluated=False,elapsed_s=time.perf_counter()-start)
    write(out/('CONTROL_FIT.json' if args.variant=='C0' else 'CANDIDATE_FIT.json'),output)
    if not result.success or not np.isfinite(result.x).all():raise RuntimeError('Solver did not converge; no restart permitted')
    print('FIT_COMPLETE',json.dumps(output),flush=True)


def metrics(pred,target,samples,meta):
    if not len(meta):return None
    ve,ie=h44.errors(pred,target,samples);w=h44.balanced_weights(meta)
    normalized=np.concatenate([ve/h44.SCALES,ie/(h44.HORIZONS*h44.SCALES)],axis=1)
    return dict(windows=len(meta),groups=len({m['group'] for m in meta}),
        combined_rms=float(np.sqrt(np.sum(w*np.mean(normalized**2,axis=1)))),
        velocity_rms=float(np.sqrt(np.sum(w*np.mean(ve*ve,axis=1)))),
        integral_rms=float(np.sqrt(np.sum(w*np.mean(ie*ie,axis=1)))),
        velocity_by_horizon=np.sqrt(np.sum(w[:,None]*ve*ve,axis=0)).tolist(),
        integral_by_horizon=np.sqrt(np.sum(w[:,None]*ie*ie,axis=0)).tolist(),
        signed_velocity_bias=np.sum(w[:,None]*ve,axis=0).tolist(),
        signed_integral_bias=np.sum(w[:,None]*ie,axis=0).tolist())


def check_models(args):
    check_lock(args.selection);freeze=read(args.freeze)
    if freeze['source_files']!=source_files() or freeze['selection_freeze_sha256']!=sha(args.selection/'SELECTION_FREEZE.json'):
        raise PermissionError('Unbound check freeze')
    models={name:read(getattr(args,name.lower())) for name in ('C0','C1')}
    for name in models:
        if sha(getattr(args,name.lower()))!=freeze['fit_sha256'][name] or not models[name]['success']:
            raise PermissionError('Fit not frozen')
    if not args.freeze_commit or len(args.freeze_commit)!=40:raise PermissionError('Published freeze commit required')
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    write(out/'started.json',dict(freeze_commit=args.freeze_commit,freeze_sha256=sha(args.freeze),source_files=source_files(),plan_sha=PLAN_SHA))
    results={};flat=[]
    for grid in ('CHECK_GRID','LEGACY_CHECK'):
        meta=read(args.selection/(grid+'.json'))
        if any(m['fold']!='check' for m in meta):raise PermissionError('Not a check grid')
        with np.load(args.selection/(grid+'.npz'),allow_pickle=False) as z:samples=z['samples'];target=z['gnss']
        predictor=h44.Predictor(samples)
        preds={n:predictor.predict(np.asarray(m['logratio'])) for n,m in models.items()}
        np.savez_compressed(out/(grid+'_predictions.npz'),**preds)
        sections={'all':list(range(len(meta)))}
        for field in ('group','phase','time_third'):
            for val in sorted({m[field] for m in meta}):sections[f'{field}:{val}']=[i for i,m in enumerate(meta) if m[field]==val]
        for group in sorted({m['group'] for m in meta}):sections['loo:'+group]=[i for i,m in enumerate(meta) if m['group']!=group]
        result={}
        for label,idx in sections.items():
            result[label]={n:metrics(p[idx],target[idx],samples[idx],[meta[i] for i in idx]) for n,p in preds.items()}
            for n,v in result[label].items():
                if v is not None:flat.append(dict(grid=grid,section=label,model=n,**v))
        results[grid]=result
    common=results['CHECK_GRID'];a=common['all']['C0'];b=common['all']['C1'];fail=[]
    gain=1-b['combined_rms']/a['combined_rms'] if a['combined_rms']>0 else None
    if gain is None or gain<.02:fail.append('insufficient_common_grid_gain')
    for metric in ('velocity_rms','integral_rms'):
        if b[metric]>a[metric]*1.005+1e-12:fail.append('aggregate:'+metric)
    improved=0;loo=[]
    for label,section in common.items():
        if label.startswith('group:'):
            if section['C1']['combined_rms']<section['C0']['combined_rms']:improved+=1
            for metric in ('combined_rms','velocity_rms','integral_rms'):
                if section['C1'][metric]>section['C0'][metric]*1.05+1e-12:fail.append(label+':'+metric)
        if label.startswith('loo:'):
            v0=section['C0']['combined_rms'];v1=section['C1']['combined_rms'];g=1-v1/v0 if v0 else None
            loo.append(dict(omitted_group=label[4:],gain_fraction=g))
            if g is None or g<=0:fail.append(label+':no_gain')
    if improved<2:fail.append('fewer_than_two_improved_groups')
    decision=dict(passed=not fail,reasons=fail,combined_gain_fraction=gain,improved_groups=improved,
                  leave_one_group_out=loo,common_check_windows=a['windows'],common_check_groups=a['groups'])
    csv_write(out/'CHECK_RESULTS.csv',flat)
    csv_write(out/'PER_GROUP.csv',[r for r in flat if r['section'].startswith('group:')])
    write(out/'CHECK_METRICS.json',results);write(out/'CHECK_DECISION.json',decision)
    print('CHECK_COMPLETE',json.dumps(decision),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='stage',required=True)
    a=s.add_parser('enumerate')
    for key in ('lock','teacher','source-receipt','data-root','h44-evidence'):a.add_argument('--'+key,type=Path,required=True)
    a.add_argument('--source-sha',required=True)
    f=s.add_parser('fit');f.add_argument('--selection',type=Path,required=True);f.add_argument('--variant',choices=('C0','C1'),required=True);f.add_argument('--control',type=Path)
    c=s.add_parser('check')
    for key in ('selection','c0','c1','freeze'):c.add_argument('--'+key,type=Path,required=True)
    c.add_argument('--freeze-commit',required=True)
    for parser in (a,f,c):parser.add_argument('--output',type=Path,required=True)
    args=p.parse_args();{'enumerate':enumerate_anchors,'fit':fit_variant,'check':check_models}[args.stage](args)
if __name__=='__main__':main()
