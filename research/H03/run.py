#!/usr/bin/env python3
"""H03: three TRAIN-only proxies, committed freeze, one unchanged validation.

No test measurement loader. GNSS is only read by Store's validation role and
passed to the unchanged external evaluator, never to the observer.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import datetime
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/finalization'), str(ROOT/'tools/research_v6')]
import evaluate as ev
_spec = importlib.util.spec_from_file_location('_h03_v6', ROOT/'tools/research_v6/compare.py')
v6 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v6)
from scipy.signal import savgol_filter

ex, np = ev.ex, ev.np
BASELINE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
PLAN = ROOT/'research/H03/PLAN.md'
VARIANTS = {'adaptive_v5': 0., 'H03_w020': .2, 'H03_w030': .3, 'H03_w040': .4}
OPS = dict(rate_hz=20., alignment_delay_s=0.)
IMMUTABLE = [
    'tools/finalization/evaluate.py', 'tools/research_v3/experiment.py',
    'tools/research_v3/manifest.py', 'tools/export_bags.py',
    'research/split_v3.json', 'research/plan_v3.json',
    'tools/research_v6/compare.py',
    'src/reserve_odometry/reserve_odometry/timeline.py',
    'src/reserve_odometry/reserve_odometry/node.py',
    'src/reserve_odometry/reserve_odometry/route.py',
    'src/reserve_odometry/config/default.yaml',
    'src/reserve_odometry/config/adaptive_v5.yaml',
    'src/reserve_odometry/config/candidates_v3/balanced_physics.json',
]
SELECTED = None


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def config(window):
    base = json.loads((ROOT/'src/reserve_odometry/config/candidates_v3/balanced_physics.json').read_text())['config']
    return ex.Config(**(base | dict(adaptation_tau_s=.5, adaptation_window_s=window)))


def integrity():
    hashes = {}
    for name in IMMUTABLE:
        original = subprocess.check_output(['git', 'show', BASELINE+':'+name], cwd=ROOT)
        current = (ROOT/name).read_bytes()
        if current != original:
            raise AssertionError('Common baseline/evaluator file changed: '+name)
        hashes[name] = digest_bytes(current)
    return dict(passed=True, baseline=BASELINE, unchanged_sha256=hashes)


def sources():
    hashes = ev.protected_files()
    for name in ['research/H03/PLAN.md', 'research/H03/run.py',
                 'research/H03/test_h03.py', 'research/H03/algorithm.patch',
                 '.github/workflows/research-H03.yml']:
        hashes[name] = ev.sha(ROOT/name)
    return hashes


def provenance():
    return dict(hypothesis='H03', baseline=BASELINE,
                source_ref=os.environ.get('GITHUB_SHA', 'local'),
                run_id=os.environ.get('GITHUB_RUN_ID'),
                run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),
                utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                source_sha256=sources(), immutable=integrity(),
                plan_sha256=ev.sha(PLAN), python=platform.python_version(),
                numpy=np.__version__, test_evaluated=False, operational=OPS)


class TraceObserver(ex.Observer):
    """Offline instrumentation only; production Estimate/API is unchanged."""
    def reset(self, **kwargs):
        super().reset(**kwargs)
        self.last_a = None
        self.last_a_stamp = None

    def _wheel_acceleration(self, tz, z, old):
        value = super()._wheel_acceleration(tz, z, old)
        self.last_a, self.last_a_stamp = value, tz
        return value


def trace(events, cfg):
    observer = TraceObserver(cfg)
    timeline = ev.Timeline(observer, rate_hz=20., delay_s=0.)
    rows = []
    max_history = 0
    for t, channel, value in events:
        timeline.ingest(int(channel), ex.Sample(float(t), float(value)))
        for estimate, held in timeline.advance():
            if estimate.mode == 'WAITING_FOR_INITIALIZATION':
                continue
            if any(s is not None and s.t > estimate.t+1e-9 for s in held):
                raise AssertionError('Causal error in train replay')
            available = (observer.adapt_previous is not None and observer.last_a is not None
                         and observer.last_a_stamp is not None
                         and observer.last_a_stamp == observer.adapt_previous.t
                         and 0 <= estimate.t-observer.last_a_stamp <= cfg.max_age_s)
            rows.append((estimate.t, observer.last_a if available else np.nan,
                         estimate.disturbance, estimate.v))
            max_history = max(max_history, len(observer.adapt_history))
    if max_history > 7:
        raise AssertionError('Unbounded H03 history')
    return np.asarray(rows, float).reshape(-1, 4), dict(
        resets=timeline.resets, dropped=timeline.dropped, max_history=max_history)


def held_grid(array, t):
    result = np.full((len(t), 3), np.nan)
    if not len(array):
        return result
    index = np.searchsorted(array[:, 0], t+1e-9, side='right')-1
    safe = np.maximum(index, 0)
    good = (index >= 0) & (t-array[safe, 0] <= .051)
    result[good] = array[safe[good], 1:]
    return result


def rms(values):
    return float(np.sqrt(np.mean(values*values))) if len(values) else None


def grouped(rows, name, key):
    groups = {}
    for row in rows:
        value = row.get('models', {}).get(name, {}).get(key)
        if value is not None:
            groups.setdefault(row['group'], []).append(value)
    return float(np.mean([np.mean(v) for v in groups.values()])) if groups else None


def train(output):
    output.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    info = provenance()
    store = ex.Store()
    ev.save(output/'started.json', info | dict(stage='train', requested_bags=store.plan['splits']['train']))
    rows = []
    for bag in store.plan['splits']['train']:
        events, refs = store.load(bag, 'train')
        if any(refs.values()):
            raise AssertionError('Train must not contain GNSS labels')
        ev.save(output/'access.json', dict(test_evaluated=False, access=store.access))
        grid = ex.grid_channels(events)
        row = dict(bag=bag, group=store.records[bag]['group'], models={})
        if grid is None or len(grid[0]) < 11:
            row['unavailable'] = 'Insufficient wheel grid'
            rows.append(row)
            ev.save(output/'bags'/(bag+'.json'), row)
            continue
        t, u, f, r, valid = grid
        velocity = .5*(f+r)
        target = savgol_filter(velocity, 11, 2, deriv=1, delta=.1)
        mask = valid & (np.abs(f-r)<.15) & (velocity>.5) & (velocity<35.) & (np.abs(u)<=1.)
        mask = (np.convolve(mask.astype(int), np.ones(11, int), mode='same')==11) & (t>2.)
        aligned = {}
        runtimes = {}
        for name, window in VARIANTS.items():
            values, runtimes[name] = trace(events, config(window))
            aligned[name] = held_grid(values, t)
        common = mask.copy()
        for name, values in aligned.items():
            finite = np.all(np.isfinite(values), axis=1)
            runtimes[name]['individual_proxy_samples'] = int(np.sum(mask & finite))
            common &= finite
        common[:2] = False
        triples = common[2:] & common[1:-1] & common[:-2]
        row.update(wheel_mask_samples=int(mask.sum()), common_samples=int(common.sum()),
                   continuous_triples=int(triples.sum()), runtime=runtimes,
                   common_mask_sha256=digest_bytes(common.tobytes()),
                   events_sha256=digest_bytes(events.tobytes()),
                   target_sha256=digest_bytes(target.tobytes()))
        index = np.flatnonzero(common)
        for name, values in aligned.items():
            lag_errors = [rms(values[index, 0]-target[index-k]) for k in range(3)]
            roughness = rms(np.diff(values[:, 1], n=2)[triples])
            row['models'][name] = dict(accel_proxy_rmse=lag_errors[0], roughness=roughness,
                                       **{'lag_rmse_'+str(k): value for k,value in enumerate(lag_errors)})
        rows.append(row)
        ev.save(output/'bags'/(bag+'.json'), row)
        print('TRAIN_CHECKPOINT', bag, row['common_samples'], flush=True)
    aggregates = {}
    for name in VARIANTS:
        agg = {key: grouped(rows, name, key) for key in
               ['accel_proxy_rmse', 'roughness', 'lag_rmse_0', 'lag_rmse_1', 'lag_rmse_2']}
        lag_scores = [agg['lag_rmse_'+str(k)] for k in range(3)]
        agg['lag_s'] = .1*min(range(3), key=lambda k: lag_scores[k]) if all(x is not None for x in lag_scores) else None
        aggregates[name] = agg
    base = aggregates['adaptive_v5']
    eligible = []
    for name in list(VARIANTS)[1:]:
        value = aggregates[name]
        reasons = []
        if any(value[k] is None or base[k] is None for k in ['accel_proxy_rmse','roughness','lag_s']):
            reasons.append('missing_proxy_data')
        else:
            if value['accel_proxy_rmse'] > 1.05*base['accel_proxy_rmse']:
                reasons.append('acceleration_proxy_regression')
            if value['roughness'] > .95*base['roughness']:
                reasons.append('insufficient_noise_reduction')
            if value['lag_s'] > base['lag_s']+.1+1e-12:
                reasons.append('additional_lag')
        value['proxy_rejection_reasons'] = reasons
        value['proxy_eligible'] = not reasons
        if not reasons:
            eligible.append(name)
    selected = min(eligible, key=lambda n: (aggregates[n]['roughness'], VARIANTS[n])) if eligible else 'H03_w020'
    results = info | dict(stage='train', rows=rows, aggregates=aggregates, selected=selected,
                         train_proxy_failed=not bool(eligible), elapsed_s=time.perf_counter()-start,
                         interpretation='Wheel-derived diagnostic proxies, NOT ground-truth accuracy')
    ev.save(output/'results.json', results)
    frozen = info | dict(stage='candidate_freeze', candidate=selected, window_s=VARIANTS[selected],
                        candidate_config=asdict(config(VARIANTS[selected])),
                        baseline_config=asdict(config(0.)),
                        train_results_sha256=ev.sha(output/'results.json'),
                        train_proxy_failed=not bool(eligible), aggregates=aggregates,
                        next_stage='Only one validation, after this file is committed')
    ev.save(output/'freeze.json', frozen)
    with (output/'per_bag.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['bag','group','model','common_samples','accel_proxy_rmse','roughness','lag_rmse_0','lag_rmse_1','lag_rmse_2'])
        for row in rows:
            for name, metrics in row['models'].items():
                writer.writerow([row['bag'],row['group'],name,row['common_samples']]+[metrics[k] for k in ['accel_proxy_rmse','roughness','lag_rmse_0','lag_rmse_1','lag_rmse_2']])
    print(json.dumps(dict(selected=selected, train_proxy_failed=not bool(eligible), aggregates=aggregates),indent=2),flush=True)


def init_worker(frozen):
    global SELECTED
    SELECTED = frozen


def validate_bag(bag):
    store = ex.Store()
    events, refs = store.load(bag, 'validation')
    models = {'baseline_v2': ex.Config(**SELECTED['baseline_config']),
              'balanced_physics': ex.Config(**SELECTED['candidate_config'])}
    clean = dict(bag=bag, group=store.records[bag]['group'], **ev.score(events,refs,models,OPS))
    stress = []
    grid = ex.grid_channels(events)
    # Exact v6 anchor, durations, fault transformations and scoring windows.
    if grid is not None:
        t,u,f,r,valid = grid
        indices = np.flatnonzero(valid & ((f+r)/2 > 2.) & (t > max(25., .1*t[-1])) & (t < t[-1]-25.))
        if len(indices):
            anchor = float(t[indices[0]])
            for kind,duration in [('bias',5.),('dropout',5.),('dropout',10.),('lock',3.)]:
                fault = dict(kind=kind,start=anchor,end=anchor+duration)
                window = events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]
                stress.append(dict(bag=bag,group=store.records[bag]['group'],fault=fault,
                                   **ev.score(window,refs,models,OPS,fault)))
    return clean,stress,store.access


def reproduction(clean):
    previous = json.loads((ROOT/'reports/research_v5/round3/results.json').read_text())
    by_bag = {row['bag']:row for row in previous['clean']}
    count, maximum, errors = 0, 0., []
    for row in clean:
        for receiver, scores in row['receivers'].items():
            a = scores['baseline_v2']
            b = by_bag[row['bag']]['receivers'][receiver]['adaptation_05s']
            for key in ['rmse','mae','bias','p95','n','coverage','false_stop_samples']:
                x,y = a.get(key),b.get(key)
                if x is None or y is None:
                    if x != y:
                        errors.append([row['bag'],receiver,key,x,y])
                else:
                    count += 1
                    maximum = max(maximum,abs(x-y))
                    if abs(x-y)>1e-10:
                        errors.append([row['bag'],receiver,key,x,y])
    return dict(compared_numeric_fields=count,max_absolute_delta=maximum,passed=not errors,errors=errors)


def acceptance(clean, stress, reproduced, frozen):
    names=['baseline_v2','balanced_physics']
    summaries={name:v6.summary(clean,stress,name) for name in names}
    base,candidate=summaries['baseline_v2'],summaries['balanced_physics']
    reasons=[]
    if not reproduced['passed']:
        reasons.append('baseline_reproduction_failed')
    changes={}
    for key in ['clean_rmse','fault_rmse','pooled_rmse','distance_rmse']:
        a,b=candidate[key],base[key]
        if a is None or b is None:
            reasons.append('missing_reference:'+key)
            changes[key]=None
        elif b==0:
            changes[key]=0. if a==0 else None
            if a>0: reasons.append('zero_baseline_regression:'+key)
        else:
            changes[key]=a/b-1
    if all(changes[k] is not None for k in ['clean_rmse','fault_rmse']):
        if changes['clean_rmse']>-.02 and changes['fault_rmse']>-.05:
            reasons.append('insufficient_gain')
    for key in ['clean_rmse','fault_rmse','pooled_rmse']:
        if changes[key] is not None and changes[key]>.005:
            reasons.append('aggregate_regression:'+key)
    if changes['distance_rmse'] is not None and changes['distance_rmse']>.01:
        reasons.append('distance_regression')
    if candidate['unrecovered']>base['unrecovered']:
        reasons.append('unrecovered_increase')
    regressions=[]
    for stage,rows in [('clean',clean),('fault',stress)]:
        for row in rows:
            if row['runtime']['balanced_physics']['causal_errors'] or row['runtime']['balanced_physics']['resets']:
                reasons.append('causality_or_reset:'+row['bag'])
            for receiver,scores in row['receivers'].items():
                a,b=scores['balanced_physics'],scores['baseline_v2']
                label=row['bag']+'/'+receiver
                if a['n']!=b['n'] or a['coverage']!=b['coverage']:
                    reasons.append('coverage:'+stage+':'+label)
                if a.get('false_stop_samples',0)>b.get('false_stop_samples',0):
                    reasons.append('false_stops:'+stage+':'+label)
                if stage=='clean' and b['rmse'] is not None and (a['rmse'] is None or a['rmse']>b['rmse']+max(.005,.05*b['rmse'])):
                    reasons.append('bag_regression:'+label)
                key='rmse' if stage=='clean' else 'event_rmse'
                if b.get(key) is not None and a.get(key) is not None and a[key]>b[key]:
                    regressions.append(dict(stage=stage,bag=row['bag'],receiver=receiver,
                        fault=row.get('fault'),metric=key,baseline=b[key],candidate=a[key],
                        absolute_change=a[key]-b[key],relative_change=a[key]/b[key]-1 if b[key] else None))
    regressions.sort(key=lambda r:r['absolute_change'],reverse=True)
    data_missing=any(r.startswith('missing_reference:') for r in reasons)
    return dict(candidate=frozen['candidate'],summary=summaries,relative_change=changes,
                eligible=not reasons,train_proxy_failed=frozen['train_proxy_failed'],
                rejection_reasons=sorted(set(reasons)),all_rmse_regressions=regressions,
                conclusion=('insufficient_data' if data_missing else 'rejected' if reasons else 'confirmed_on_reused_validation'),
                test_evaluated=False,independent_final_test=False,
                limitations=['Reused validation, not independent generalization',
                             'Train acceleration target derives from wheels, not independent ground truth',
                             'Scalar reanchored distance, not xyz or terminal drift',
                             'No installed-ROS latency/resource benchmark for H03',
                             'Common-mode wheel faults remain unidentifiable'])


def write_validation_csv(output,clean,stress):
    columns=['stage','bag','group','receiver','model','fault_kind','fault_start_s','fault_end_s',
             'n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s','false_stop_samples','distance_rmse']
    with (output/'per_bag.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=columns)
        writer.writeheader()
        for stage,rows in [('clean',clean),('fault',stress)]:
            for row in rows:
                for receiver,scores in row['receivers'].items():
                    for model in ['baseline_v2','balanced_physics']:
                        metrics=scores[model]
                        fault=row.get('fault',{})
                        line=dict(stage=stage,bag=row['bag'],group=row['group'],receiver=receiver,model=model,
                                  fault_kind=fault.get('kind'),fault_start_s=fault.get('start'),fault_end_s=fault.get('end'),
                                  distance_rmse=metrics.get('distance_surrogate',{}).get('reanchored_span_rmse_m'))
                        for key in columns[8:-1]:line[key]=metrics.get(key)
                        writer.writerow(line)


def validate(output,freeze_path,workers):
    frozen=json.loads(freeze_path.read_text())
    if frozen['baseline']!=BASELINE or frozen['source_sha256']!=sources():
        raise AssertionError('Algorithm/evaluator/plan changed after candidate freeze')
    if frozen['candidate'] not in VARIANTS or frozen['window_s']!=VARIANTS[frozen['candidate']]:
        raise AssertionError('Unregistered candidate')
    if frozen['candidate_config']!=asdict(config(frozen['window_s'])) or frozen['baseline_config']!=asdict(config(0.)):
        raise AssertionError('Frozen model differs')
    if ev.sha(freeze_path.parent/'results.json')!=frozen['train_results_sha256']:
        raise AssertionError('Train evidence changed')
    relative=str(freeze_path.resolve().relative_to(ROOT))
    commit=os.environ.get('H03_FREEZE_SHA') or subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    committed=subprocess.check_output(['git','show',commit+':'+relative],cwd=ROOT)
    if digest_bytes(committed)!=ev.sha(freeze_path):
        raise AssertionError('Freeze is not committed BEFORE validation')
    output.mkdir(parents=True,exist_ok=False)
    info=provenance() | dict(stage='validation',freeze_sha256=ev.sha(freeze_path),freeze_commit=commit,
                             candidate=frozen['candidate'],aliases={'baseline_v2':'adaptive_v5','balanced_physics':frozen['candidate']})
    store=ex.Store()
    ev.save(output/'started.json',info | dict(requested_bags=store.plan['splits']['validation']))
    start=time.perf_counter()
    clean,stress,access=[],[],[]
    with ProcessPoolExecutor(max_workers=workers,initializer=init_worker,initargs=(frozen,)) as pool:
        for row,faults,journal in pool.map(validate_bag,store.plan['splits']['validation']):
            clean.append(row);stress.extend(faults);access.extend(journal)
            ev.save(output/'bags'/(row['bag']+'.json'),dict(clean=row,stress=faults))
            ev.save(output/'access.json',dict(test_evaluated=False,access=access))
            print('VALIDATION_CHECKPOINT',row['bag'],flush=True)
    reproduced=reproduction(clean)
    result=info | dict(clean=clean,stress=stress,baseline_reproduction=reproduced,
                       elapsed_s=time.perf_counter()-start,bags=len(clean),fault_scenarios=len(stress),
                       models={'baseline_v2':frozen['baseline_config'],'balanced_physics':frozen['candidate_config']})
    ev.save(output/'results.json',result)
    decision=acceptance(clean,stress,reproduced,frozen)
    ev.save(output/'decision.json',decision)
    write_validation_csv(output,clean,stress)
    print(json.dumps({k:v for k,v in decision.items() if k!='all_rmse_regressions'},indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['integrity','train','validate'])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--freeze',type=Path)
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    if not 1<=args.workers<=8:
        parser.error('workers must be between 1 and 8')
    if args.stage=='integrity':
        ev.save(args.output,integrity())
    elif args.stage=='train':
        train(args.output)
    elif args.freeze is None:
        parser.error('validate requires a committed --freeze')
    else:
        validate(args.output,args.freeze,args.workers)


if __name__=='__main__':
    main()
