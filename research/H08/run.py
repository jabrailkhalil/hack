"""One preregistered H08 candidate. Uses the pinned score and v6 gates unchanged."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/research_v6'))
import compare as v6

ev, ex, np = v6.ev, v6.ex, v6.np
BASE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
NAME = 'h08_exact_midpoint'
ALIASES = v6.ALIASES
OPS = dict(rate_hz=20., alignment_delay_s=0.)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()


def models():
    base = json.loads((ROOT/'src/reserve_odometry/config/candidates_v3/balanced_physics.json').read_text())['config']
    adaptive = base | {'adaptation_tau_s': .5}
    actual = json.loads((ROOT/'src/reserve_odometry/config/adaptive_v5.json').read_text())['config']
    if adaptive != actual:
        raise ValueError('Baseline profile mismatch')
    return {'baseline_v2': ex.Config(**base), 'balanced_physics': ex.Config(**adaptive),
            NAME: ex.Config(**(adaptive | {'numerical_prediction': 1.0}))}


def hashes():
    result = ev.protected_files()
    for path in [ROOT/'research/H08/PROTOCOL.md', ROOT/'research/H08/RUNTIME_PLAN.md',
                 ROOT/'research/H08/run.py', ROOT/'research/H08/apply.py',
                 ROOT/'research/H08/tests/test_numerics.py',
                 ROOT/'src/reserve_odometry/config/h08_exact_midpoint.json']:
        result[str(path.relative_to(ROOT))] = ev.sha(path)
    return result


def check_pinned():
    allowed = {'src/reserve_odometry/reserve_odometry/core.py',
               'src/reserve_odometry/reserve_odometry/numerics_h08.py',
               'src/reserve_odometry/config/h08_exact_midpoint.yaml'}
    for path, digest in ev.protected_files().items():
        if path in allowed:
            continue
        old = subprocess.check_output(['git', 'show', BASE+':'+path], cwd=ROOT)
        if hashlib.sha256(old).hexdigest() != digest:
            raise ValueError('Protected baseline file changed: '+path)
    if (ROOT/'src/reserve_odometry/config/default.yaml').read_bytes() != (ROOT/'src/reserve_odometry/config/adaptive_v5.yaml').read_bytes():
        raise ValueError('Default is no longer the pinned adaptive_v5')
    models()


def provenance():
    return dict(baseline_commit=BASE, source_commit=git('rev-parse', 'HEAD'),
                candidate=NAME, candidate_count=1, tuning_performed=False,
                utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                source_sha256=hashes(), python=platform.python_version(), numpy=np.__version__,
                platform=platform.platform(), run_id=os.environ.get('GITHUB_RUN_ID'),
                run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'), test_evaluated=False,
                operational=OPS, models={ALIASES.get(k,k):asdict(c) for k,c in models().items()})


def timed_replay(events, config):
    wall, cpu = time.perf_counter(), time.process_time()
    array, runtime = ev.replay(events, config, OPS)
    cpu, wall = time.process_time()-cpu, time.perf_counter()-wall
    n = len(array)
    return array, runtime, dict(wall_s=wall, cpu_s=cpu, outputs=n,
        wall_us_per_output=wall/n*1e6 if n else None,
        cpu_us_per_output=cpu/n*1e6 if n else None)


def development(output):
    output.mkdir(parents=True, exist_ok=False)
    ev.save(output/'started.json', provenance())
    store = ex.Store(); configs = models(); rows = []; bench_events = None
    for bag in store.plan['splits']['train']:
        events, refs = store.load(bag, 'train')
        assert not any(refs.values()), 'Train must not read reference measurements'
        ev.save(output/'access.json', dict(test_evaluated=False, access=store.access))
        arrays, runtimes, costs = {}, {}, {}
        for name in ('balanced_physics', NAME):
            arrays[name], runtimes[name], costs[name] = timed_replay(events, configs[name])
        a, b = arrays['balanced_physics'], arrays[NAME]
        if a.shape != b.shape or not np.array_equal(a[:,0], b[:,0]):
            raise AssertionError('Train output schedule differs: '+bag)
        if runtimes[NAME]['causal_errors'] or runtimes[NAME]['resets'] != runtimes['balanced_physics']['resets']:
            raise AssertionError('Causality or unexpected reset: '+bag)
        row = dict(bag=bag, group=store.records[bag]['group'], outputs=len(a),
                   runtime=runtimes, timing=costs, reference_accuracy=None,
                   terminal_positions_m={n:float(v[-1,2]) if len(v) else None for n,v in arrays.items()},
                   max_abs_speed_delta_between_models=float(np.max(abs(a[:,1]-b[:,1]))) if len(a) else None,
                   note='Positions and model deltas are not errors against ground truth')
        rows.append(row); ev.save(output/'bags'/(bag+'.json'), row)
        if bench_events is None and len(a)>1200:
            start = float(events[:,0].min()); bench_events = events[events[:,0]<=start+60.].copy(); bench_bag=bag
        print('TRAIN_CHECKPOINT', bag, len(a), flush=True)
    if bench_events is None:
        raise ValueError('No train bag with enough outputs for the fixed 60-second benchmark')
    trials = []
    for repeat in range(6):
        order = ('balanced_physics', NAME) if repeat%2==0 else (NAME, 'balanced_physics')
        for name in order:
            _, _, cost = timed_replay(bench_events, configs[name])
            trials.append(dict(repeat=repeat, warmup=repeat==0, model=ALIASES.get(name,name), **cost))
    ev.save(output/'benchmark.json', dict(bag=bench_bag, seconds=60, trials=trials,
        scope='Python replay, including timeline and output collection; NOT ROS latency',
        benchmark_order='alternating, first pair warmup, five measured pairs'))
    ev.save(output/'results.json', dict(**provenance(), rows=rows, access=store.access,
                                      passed=True, ground_truth_accuracy_measured=False))


def freeze(path, development_path):
    development_result = json.loads((development_path/'results.json').read_text())
    if not development_result['passed'] or development_result['source_sha256'] != hashes():
        raise ValueError('Development checks not complete for these sources')
    if path.exists():
        raise FileExistsError('Do not overwrite the pre-validation freeze')
    ev.save(path, dict(**provenance(), selected=NAME, development_results_sha256=ev.sha(development_path/'results.json'),
                       selection_rule='Exactly one candidate fixed before any measurement; no tuning',
                       validation_opened=False))


def validate_bag(arguments):
    bag, output = arguments
    store = ex.Store(); events, refs = store.load(bag, 'validation'); configs = models()
    ev.save(output/'access'/(bag+'.json'), dict(test_evaluated=False, access=store.access))
    clean = dict(bag=bag, group=store.records[bag]['group'], **ev.score(events, refs, configs, OPS))
    stress = []; grid = ex.grid_channels(events)
    # Identical fault construction to the pinned v6 validate_bag, no new masks.
    if grid is not None:
        t, u, f, r, valid = grid
        indices = np.flatnonzero(valid & ((f+r)/2>2.) & (t>max(25., .1*t[-1])) & (t<t[-1]-25.))
        if len(indices):
            anchor = float(t[indices[0]])
            for kind, duration in [('bias',5.), ('dropout',5.), ('dropout',10.), ('lock',3.)]:
                fault = dict(kind=kind, start=anchor, end=anchor+duration)
                window = events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]
                stress.append(dict(bag=bag, group=store.records[bag]['group'], fault=fault,
                                   **ev.score(window, refs, configs, OPS, fault)))
    for row in [clean]+stress:
        for internal, public in ALIASES.items():
            row['runtime'][public] = row['runtime'].pop(internal)
            for scores in row['receivers'].values():
                scores[public] = scores.pop(internal)
    ev.save(output/'bags'/(bag+'.json'), dict(clean=clean, stress=stress))
    return clean, stress, store.access


def csv_results(output, clean, stress):
    fields = ['phase','bag','group','receiver','model','fault_kind','fault_start','fault_end',
              'n','coverage','rmse','mae','bias','p95','distance_rmse','event_rmse','recovery_s','false_stop_samples']
    with (output/'per_bag.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for phase, rows in [('clean',clean), ('fault',stress)]:
            for row in rows:
                fault = row.get('fault',{})
                for receiver,scores in row['receivers'].items():
                    for name in ('v4_default','v5_adaptive_05s',NAME):
                        metrics=scores[name]
                        item=dict(phase=phase,bag=row['bag'],group=row['group'],receiver=receiver,model=name,
                                  fault_kind=fault.get('kind'),fault_start=fault.get('start'),fault_end=fault.get('end'),
                                  distance_rmse=metrics.get('distance_surrogate',{}).get('reanchored_span_rmse_m'))
                        item.update({k:metrics.get(k) for k in fields if k not in item})
                        writer.writerow(item)


def validation(output, frozen_path, workers):
    locked=json.loads(frozen_path.read_text())
    if locked['selected']!=NAME or locked['source_sha256']!=hashes():
        raise ValueError('Candidate or measurement sources changed after freeze')
    output.mkdir(parents=True,exist_ok=False); ev.save(output/'started.json',provenance())
    store=ex.Store(); clean=[]; stress=[]; access=[]; start=time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row,faults,journal in pool.map(validate_bag,[(b,output) for b in store.plan['splits']['validation']]):
            clean.append(row); stress.extend(faults); access.extend(journal)
            ev.save(output/'access.json',dict(test_evaluated=False,access=access))
            print('VALIDATION_CHECKPOINT',row['bag'],flush=True)
    reproduction=v6.reproduce_published_v5(clean)
    result=dict(**provenance(), frozen_sha256=ev.sha(frozen_path),clean=clean,stress=stress,
                baseline_reproduction=reproduction,elapsed_s=time.perf_counter()-start)
    ev.save(output/'results.json',result)
    decision=v6.decide(clean,stress,['v4_default','v5_adaptive_05s',NAME])
    entry=decision['candidates'][NAME]; base=decision['candidates']['v5_adaptive_05s']
    # Preserve the original gate; enforce the user's explicit pooled guard too.
    pooled_failure=entry['pooled_rmse']>1.005*base['pooled_rmse']
    decision['h08_pooled_guard_passed']=not pooled_failure
    decision['h08_accuracy_gate_passed']=entry['eligible'] and not pooled_failure
    decision['h08_verdict']='подтверждена на повторно использованном validation' if decision['h08_accuracy_gate_passed'] else 'отвергнута'
    decision['h08_runtime_gate']='see separate measured ROS runtime; accuracy pass alone cannot authorize promotion'
    decision['h08_additional_reasons']=['pooled_regression'] if pooled_failure else []
    ev.save(output/'decision.json',decision); csv_results(output,clean,stress)
    regressions=[]
    for row in clean:
        for receiver,scores in row['receivers'].items():
            a,b=scores[NAME],scores['v5_adaptive_05s']
            if a['rmse'] is not None and b['rmse'] is not None:
                regressions.append(dict(bag=row['bag'],receiver=receiver,baseline_rmse=b['rmse'],candidate_rmse=a['rmse'],
                                        delta_mps=a['rmse']-b['rmse'],change_percent=100*(a['rmse']/b['rmse']-1) if b['rmse'] else None,
                                        violates_guard=a['rmse']>b['rmse']+max(.005,.05*b['rmse'])))
    ev.save(output/'regressions.json',sorted(regressions,key=lambda x:x['delta_mps'],reverse=True))
    lines=['# H08 — фактический результат','',decision['h08_verdict'],'',
           '| Метрика | adaptive_v5 | H08 | Изменение |','|---|---:|---:|---:|']
    for key in ['clean_rmse','fault_rmse','pooled_rmse','distance_rmse']:
        lines.append(f'| {key} | {base[key]:.12g} | {entry[key]:.12g} | {100*(entry[key]/base[key]-1):+.6f}% |')
    lines += ['', 'Причины v6 gate: '+', '.join(entry['rejection_reasons']),
              'Дополнительные причины: '+', '.join(decision['h08_additional_reasons']),
              '', 'Это повторно использованный validation, не независимый final test. Runtime проверяется отдельно.',
              'Полные scores: results.json, per_bag.csv, bags/*.json. Ошибки без reference не заменены нулём.']
    (output/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(decision,indent=2,ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['development','freeze','validation'],required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--freeze',type=Path)
    parser.add_argument('--development',type=Path)
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    if not 1<=args.workers<=8: parser.error('workers must be in [1,8]')
    check_pinned()
    if args.stage=='development':
        if args.output is None: parser.error('--output is required')
        development(args.output)
    elif args.stage=='freeze':
        if args.freeze is None or args.development is None: parser.error('--freeze and --development are required')
        freeze(args.freeze,args.development)
    else:
        if args.output is None or args.freeze is None: parser.error('--output and --freeze are required')
        validation(args.output,args.freeze,args.workers)


if __name__=='__main__':
    main()
