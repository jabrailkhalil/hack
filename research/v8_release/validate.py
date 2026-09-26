"""Frozen residual070: validation-only admission. No training, tuning or promotion.

Imports the measured observer, original scorer and fixed fault generators. Raw
reference never enters the observer. Result is only numerical admission; ROS and
installed-default verification are separate mandatory release checks.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TARGET = ROOT / 'research/v8_targeted'
NAMES = ('main', 'disturbance_070')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()


def verify_frozen():
    freeze = json.loads((TARGET / 'FREEZE.json').read_text())
    for name, h in freeze['source_sha256'].items():
        if sha(TARGET / name) != h: raise ValueError('Frozen research source changed: ' + name)
    pins = json.loads((TARGET / 'BASELINE_PINS.json').read_text())
    for name, h in pins.items():
        if sha(ROOT / name) != h: raise ValueError('Frozen runtime/scorer changed: ' + name)
    return {'research': freeze['source_sha256'], 'baseline': pins}


verify_frozen()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


e = load('release_frozen_evaluator', TARGET / 'evaluate.py')
supp = load('release_frozen_supplements', TARGET / 'supplemental.py')
np = e.np


class ValidationStore(e.ex.Store):
    def load(self, bag, purpose='validation'):
        # Role veto before checking/reading/opening the DB.
        if purpose != 'validation' or bag not in self.plan['splits']['validation'] or self.records[bag]['split'] != 'validation':
            raise PermissionError('Release runner permits validation measurements only')
        return super().load(bag, 'validation')


def fixed_models():
    result = e.c.models(NAMES)
    if result['disturbance_070'][1].disturbance_limit_mps2 != .7000000000000001:
        raise ValueError('Candidate float changed')
    from dataclasses import asdict
    a = asdict(result['main'][1]); b = asdict(result['disturbance_070'][1])
    if [k for k in a if a[k] != b[k]] != ['disturbance_limit_mps2']:
        raise ValueError('Candidate is not the single frozen parameter edit')
    return result


def integral_check(clean, changed, fault):
    if clean.shape != changed.shape or not np.array_equal(clean[:, 0], changed[:, 0]):
        raise AssertionError('Full-faulted schedule differs')
    if not np.all(np.isfinite(clean[:, :3])) or not np.all(np.isfinite(changed[:, :3])):
        raise AssertionError('Nonfinite published time/velocity/distance')
    before = clean[:, 0] < fault['start']
    if not np.array_equal(clean[before, :3], changed[before, :3]):
        raise AssertionError('Fault changed its own prefault prefix')
    if not len(clean): return {'max_error_m': None, 'terminal_delta_s_m': None, 'post10_delta_s_m': None}
    dv = changed[:, 1] - clean[:, 1]; ds = changed[:, 2] - clean[:, 2]
    integ = np.r_[0., np.cumsum(.5 * (dv[1:] + dv[:-1]) * np.diff(clean[:, 0]))]
    error = float(np.max(np.abs(ds - ds[0] - integ)))
    if error > 1e-7: raise AssertionError('Published distance integral discrepancy')
    q = fault['end'] + 10.; j = np.searchsorted(clean[:, 0], q, side='right') - 1
    return dict(max_error_m=error, terminal_delta_s_m=float(ds[-1]),
                post10_delta_s_m=float(ds[j]) if j >= 0 and clean[-1, 0] >= q else None)


def worker(args):
    bag, root, output = args
    start = time.monotonic(); s = ValidationStore(root); events, refs = s.load(bag)
    models = fixed_models()
    meta = dict(bag=bag, group=s.records[bag]['group'], db_sha256=s.records[bag]['sha256'])
    arrays, info = e.predictions(events, models)
    clean = dict(meta, **e.score_arrays(arrays, info, refs))
    direct = e.g.compare(events, refs, models)
    if clean['receivers'] != direct['receivers'] or clean['runtime'] != direct['runtime']:
        raise AssertionError('Independent clean scorer invocation differs')
    stress = []; full = []; retained = []; extras = {'low': [], 'common': [], 'slow': []}
    out = Path(output)
    np.savez_compressed(out / 'arrays' / (bag + '-clean.npz'), **arrays)
    for i, (fault, window) in enumerate(e.g.fault_windows(events)):
        stress.append(dict(meta, fault=fault, **e.g.compare(window, refs, models, fault)))
        changed, runtime = e.predictions(events, models, fault)
        retained.append(dict(fault=fault, models={n: integral_check(arrays[n], changed[n], fault) for n in NAMES}))
        full.append(dict(meta, fault=fault, **e.score_arrays(changed, runtime, refs)))
        np.savez_compressed(out / 'arrays' / (bag + '-fault-' + str(i) + '.npz'), **changed)
    for fault, window in supp.low_windows(events):
        extras['low'].append(dict(meta, fault=fault, **e.g.compare(window, refs, models, fault)))
    for name, generator in [('common', supp.common_windows), ('slow', supp.slow_windows)]:
        for fault, changed in generator(events):
            extras[name].append(dict(meta, fault=fault, **supp.compare_injected(changed, refs, models, fault)))
    result = dict(clean=clean, stress=stress, full=full, supplemental=extras, retained=retained,
                  access=s.access, independent_clean_scorer=True, elapsed_s=time.monotonic()-start)
    e.save(out / 'bags' / (bag + '.json'), result)
    print(bag, 'original', len(stress), 'supplemental', {k: len(v) for k,v in extras.items()}, flush=True)
    return result


def present(value):
    return isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value)


def aggregate_gates(primary, extra):
    reasons = []
    for scope in ('all', '30618'):
        b = primary[scope]['main']; c = primary[scope]['disturbance_070']
        for key, tol in [('clean_rmse',.005),('pooled_rmse',.005),('fault_rmse',.005),('distance_rmse',.01),('full_faulted_distance_rmse',.01)]:
            if not present(b[key]) or not present(c[key]): reasons.append(scope+':missing:'+key)
            elif c[key] > b[key]*(1+tol)+1e-12: reasons.append(scope+':regression:'+key)
        for suite in ('low','common','slow'):
            bs = extra[scope][suite]['main']; cs = extra[scope][suite]['disturbance_070']
            if not present(bs) or not present(cs): reasons.append(scope+':missing:'+suite)
            elif cs > bs*1.005+1e-12: reasons.append(scope+':regression:'+suite)
    b=primary['30618']['main']; c=primary['30618']['disturbance_070']
    clean = present(b['clean_rmse']) and present(c['clean_rmse']) and b['clean_rmse'] > 0 and c['clean_rmse'] <= b['clean_rmse']*.98
    fault = present(b['fault_rmse']) and present(c['fault_rmse']) and b['fault_rmse'] > 0 and c['fault_rmse'] <= b['fault_rmse']*.95
    if not(clean or fault): reasons.append('30618:insufficient_gain')
    return reasons


def individual_gates(suites):
    reasons=[]
    for label, items in suites.items():
        for row in items:
            case=label+':'+row['bag']+':'+str(row.get('fault',{}))
            rt=row['runtime']['disturbance_070']
            if rt['causal_errors'] or rt['resets']: reasons.append('runtime:'+case)
            for receiver, scores in row['receivers'].items():
                b=scores['main']; c=scores['disturbance_070']; key=case+':'+receiver
                if b['n']!=c['n'] or b['coverage']!=c['coverage']: reasons.append('coverage:'+key)
                if c['false_stop_samples']>b['false_stop_samples']: reasons.append('false_stop:'+key)
                if b.get('event_rmse') is not None and b.get('recovery_s') is not None and c.get('recovery_s') is None:
                    reasons.append('new_unrecovered:'+key)
                if label=='clean' and b['rmse'] is not None and (c['rmse'] is None or c['rmse'] > b['rmse']+max(.005,.05*b['rmse'])+1e-12):
                    reasons.append('per_bag_clean:'+key)
    return reasons


def fingerprint(primary):
    b=primary['all']['main']
    # Exact published unrounded v7/v8 clean/original values from PROMOTION.json.
    expected={'clean_rmse':.1145498613174081,'fault_rmse':.5382867826008657,
              'distance_rmse':4.595480653017927,'samples':698891,
              'false_stops_clean':18,'false_stops_fault':0,'unrecovered':0}
    checks={k:present(b.get(k)) and math.isclose(b[k],v,rel_tol=0.,abs_tol=1e-12) for k,v in expected.items()}
    checks['pooled_rmse_rounded']=present(b.get('pooled_rmse')) and abs(b['pooled_rmse']-.216406794)<=5e-10
    return {'passed':all(checks.values()),'checks':checks,'observed':b,'expected':expected}


def summarize(rows):
    primary=e.summarize(rows,NAMES,True)
    suites={k:[] for k in ('clean','original','full','low','common','slow')}
    for row in rows:
        suites['clean'].append(row['clean']); suites['original'].extend(row['stress']); suites['full'].extend(row['full'])
        for k,vals in row['supplemental'].items(): suites[k].extend(vals)
    extra={scope:{k:{n:e.v6.macro([r for r in suites[k] if scope=='all' or r['bag'].startswith(scope+'_')],n,'event_rmse')
                        for n in NAMES} for k in ('low','common','slow')} for scope in ('all','30618','30639')}
    fp=fingerprint(primary)
    reasons=aggregate_gates(primary,extra)+individual_gates(suites)
    if not fp['passed']: reasons.append('baseline_fingerprint')
    groups=[]
    for group in sorted({r['group'] for r in suites['clean']}):
        for kind,mask in [('group',lambda r:r['group']==group),('leave_one_group_out',lambda r:r['group']!=group)]:
            vals=list(filter(mask,suites['original']))
            groups.append(dict(group=group,kind=kind,**{n:e.v6.macro(vals,n,'event_rmse') for n in NAMES}))
    distinct=[]; seen=set()
    for row in rows:
        h=row['clean']['db_sha256']
        if h not in seen: distinct.append(row);seen.add(h)
    return dict(status='VALIDATION_PASS' if not reasons else 'VALIDATION_REJECTED', reasons=sorted(set(reasons)),
                primary=primary,supplemental=extra,baseline_fingerprint=fp,
                bags=len(rows),distinct_DBs=len(seen),scenario_counts={k:len(v) for k,v in suites.items()},
                groups=groups,distinct_DB_sensitivity=e.summarize(distinct,NAMES,True),
                role='reused_validation',candidate='v8_residual070',fitting_calls=0,
                ready_to_merge=False,installed_ROS='NOT_CERTIFIED_BY_NUMERICAL_RUNNER',final_test_opened=False)


def run(data_root, output, workers=2):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    (output/'bags').mkdir();(output/'arrays').mkdir()
    pins=verify_frozen();models=fixed_models();store=ValidationStore(data_root)
    bags=store.plan['splits']['validation']
    if len(bags)!=19:raise ValueError('All nineteen frozen validation bags are mandatory')
    start=dict(time_utc=datetime.now(timezone.utc).isoformat(),source_sha256=sha(Path(__file__)),
               pins=pins,models=e.c.manifest(NAMES),python=platform.python_version(),numpy=np.__version__,
               role='validation',bags=bags,workers=workers,fitting_calls=0)
    e.save(output/'STARTED.json',start)
    try:
        # Preflight all authorized DB hashes before decoding the first message.
        for bag in bags:
            if sha(Path(data_root)/bag/(bag+'_0.db3'))!=store.records[bag]['sha256']:raise ValueError('DB checksum '+bag)
        args=[(b,str(data_root),str(output)) for b in bags]
        with ProcessPoolExecutor(max_workers=workers) as pool: rows=list(pool.map(worker,args))
        result=summarize(rows)
        verify_frozen()
        e.save(output/'RESULT.json',result)
        e.save(output/'ACCESS.json',[a for row in rows for a in row['access']])
        e.save(output/'MANIFEST.json',{p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file()})
        return result
    except Exception as exc:
        e.save(output/'FAILURE.json',dict(status='INCOMPLETE_NOT_PASS',error=repr(exc)))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,choices=range(1,9),default=2)
    a=p.parse_args();result=run(a.data_root,a.output,a.workers)
    print(json.dumps({'status':result['status'],'reasons':result['reasons'],'primary':result['primary']},indent=2))
    raise SystemExit(0 if result['status']=='VALIDATION_PASS' else 2)
