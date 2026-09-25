#!/usr/bin/env python3
"""H01 preregistered development -> immutable freeze -> one validation run.

Only this orchestration/role-specific development loader is new. All speed,
reference, fault, distance and aggregation functions remain the baseline's.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tools/research_v6'))
import compare as v6

ev, ex, np = v6.ev, v6.ex, v6.np
BASE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
PLAN = ROOT/'research/parallel/H01/PLAN.json'
ALIASES = v6.ALIASES
OPS = dict(rate_hz=20., alignment_delay_s=0.)
_FROZEN = None


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def git_bytes(path):
    return subprocess.check_output(['git', 'show', BASE+':'+str(path)], cwd=ROOT)


def verify_sources():
    plan = json.loads(PLAN.read_text())
    if plan['baseline_commit'] != BASE:
        raise ValueError('Baseline was changed')
    fixed = plan['evaluator']['files_frozen_at_baseline'] + [
        'src/reserve_odometry/reserve_odometry/timeline.py',
        'src/reserve_odometry/reserve_odometry/node.py',
        'src/reserve_odometry/reserve_odometry/route.py',
        'src/reserve_odometry/config/adaptive_v5.json',
        'src/reserve_odometry/config/adaptive_v5.yaml',
        'src/reserve_odometry/config/default.yaml',
        'src/reserve_odometry/config/candidates_v3/balanced_physics.json']
    for path in fixed:
        if (ROOT/path).read_bytes() != git_bytes(path):
            raise ValueError('Protected baseline file changed: '+path)
    sources = fixed + ['src/reserve_odometry/reserve_odometry/core.py',
        'src/reserve_odometry/reserve_odometry/h01_projection.py',
        'research/parallel/H01/PLAN.json', 'research/parallel/H01/run.py',
        'research/parallel/H01/tests/test_h01.py']
    return {p: ev.sha(ROOT/p) for p in sources}


def configurations(ids):
    base = json.loads((ROOT/'src/reserve_odometry/config/candidates_v3/balanced_physics.json').read_text())['config']
    adaptive = json.loads((ROOT/'src/reserve_odometry/config/adaptive_v5.json').read_text())['config']
    if adaptive != base | {'adaptation_tau_s': .5}:
        raise ValueError('The adaptive_v5 target baseline differs')
    models = {'baseline_v2': ex.Config(**base), 'balanced_physics': ex.Config(**adaptive)}
    hypotheses = {h['id']: h for h in json.loads(PLAN.read_text())['variants']}
    for name in ids:
        models[name] = ex.Config(**(adaptive | {'h01_projection_gain': hypotheses[name]['h01_projection_gain']}))
    return models


class DevelopmentStore(ex.Store):
    def load(self, bag, purpose):
        if purpose != 'development':
            return super().load(bag, purpose)
        row = self.records[bag]
        if row['split'] != 'development' or bag not in self.plan['splits']['development']:
            raise PermissionError('Development membership check failed before database IO')
        path = self.root/bag/(bag+'_0.db3')
        if ev.sha(path) != row['sha256']:
            raise ValueError('Development DB checksum mismatch: '+bag)
        allowed = list(ex.CHANNELS)+list(ex.REFS)
        entry = dict(bag=bag, purpose=purpose, sha256=row['sha256'], topics=allowed)
        self.access.append(entry)
        events, refs = [], {'master': [], 'rover': []}
        origin = row['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as con:
            query = ('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                     'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic, typ, raw in con.execute(query, allowed):
                stamp, values = ev.decode(raw, typ)
                t = (stamp-origin)/1e9
                if topic in ex.CHANNELS:
                    ch = ex.CHANNELS[topic]
                    events.append((t, ch, float(values[0])/(15 if ch == 0 else 3.6)))
                else:
                    speed = math.hypot(float(values[0]), float(values[1]))
                    if math.isfinite(speed):
                        refs[ex.REFS[topic]].append((t, speed))
        return np.asarray(events, float), refs


def original_observer():
    global _FROZEN
    if _FROZEN is None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'baseline_core.py'
            path.write_bytes(git_bytes('src/reserve_odometry/reserve_odometry/core.py'))
            spec = importlib.util.spec_from_file_location('h01_original_core', path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            _FROZEN = module.Observer
    return _FROZEN


def verify_disabled(events, config, fault=None):
    actual, info = ev.replay(events, config, OPS, fault)
    active_observer = ev.Observer
    try:
        ev.Observer = original_observer()
        expected, old_info = ev.replay(events, config, OPS, fault)
    finally:
        ev.Observer = active_observer
    if not np.array_equal(actual, expected, equal_nan=True) or info != old_info:
        raise AssertionError('Disabled H01 is not identical to original baseline')
    # Hash includes timestamps, speed, distance, held-wheel diagnostics and stops.
    return dict(passed=True, outputs=len(actual), array_sha256=hashlib.sha256(actual.tobytes()).hexdigest())


def evaluate_bag(job):
    bag, role, ids, destination = job
    store = DevelopmentStore() if role == 'development' else ex.Store()
    row = store.records[bag]
    write_new(Path(destination)/'access_started'/f'{bag}.json',
              dict(bag=bag, purpose=role, sha256=row['sha256'], test_evaluated=False))
    events, refs = store.load(bag, role)
    models = configurations(ids)
    identity = [verify_disabled(events, models['balanced_physics'])]
    clean = dict(bag=bag, group=row['group'], **ev.score(events, refs, models, OPS))
    stress = []
    # Exact fault selection/window construction from baseline v6.validate_bag.
    grid = ex.grid_channels(events)
    if grid is not None:
        t, u, f, r, valid = grid
        indices = np.flatnonzero(valid & ((f+r)/2 > 2.) & (t > max(25., .1*t[-1])) & (t < t[-1]-25.))
        if len(indices):
            anchor = float(t[indices[0]])
            for kind, duration in [('bias', 5.), ('dropout', 5.), ('dropout', 10.), ('lock', 3.)]:
                fault = dict(kind=kind, start=anchor, end=anchor+duration)
                window = events[(events[:, 0] >= anchor-20) & (events[:, 0] <= anchor+duration+10.1)]
                identity.append(verify_disabled(window, models['balanced_physics'], fault))
                stress.append(dict(bag=bag, group=row['group'], fault=fault,
                                   **ev.score(window, refs, models, OPS, fault)))
    for result in [clean]+stress:
        for internal, public in ALIASES.items():
            result['runtime'][public] = result['runtime'].pop(internal)
            for scores in result['receivers'].values():
                scores[public] = scores.pop(internal)
    evidence = dict(clean=clean, stress=stress, access=store.access, baseline_identity=identity,
                    events_sha256=hashlib.sha256(events.tobytes()).hexdigest(), test_evaluated=False)
    write_new(Path(destination)/'bags'/f'{bag}.json', evidence)
    return evidence


def gates(clean, stress, ids):
    names = ['v4_default', 'v5_adaptive_05s']+list(ids)
    summaries = {name: v6.summary(clean, stress, name) for name in names}
    if any(summaries[n][key] is None for n in names for key in ('clean_rmse', 'fault_rmse', 'distance_rmse', 'pooled_rmse')):
        return None, summaries, {n: ['insufficient_reference_data'] for n in ids}
    decision = v6.decide(clean, stress, names)
    reasons = {name: list(decision['candidates'][name]['rejection_reasons']) for name in ids}
    for name in ids:
        if summaries[name]['pooled_rmse'] > summaries['v5_adaptive_05s']['pooled_rmse']*1.005:
            reasons[name].append('pooled_rmse_regression')
    return decision, summaries, reasons


def export_csv(path, clean, stress, ids):
    import csv
    with path.open('x', newline='') as stream:
        fields = ['bag', 'group', 'receiver', 'scenario', 'model', 'n', 'coverage', 'rmse', 'mae', 'bias',
                  'p95', 'event_rmse', 'recovery_s', 'false_stop_samples', 'distance_rmse']
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for row in clean+stress:
            fault = row.get('fault')
            scenario = (fault['kind']+'_'+str(fault['end']-fault['start'])+'s') if fault else 'clean'
            for receiver, scores in row['receivers'].items():
                for name in ['v5_adaptive_05s']+list(ids):
                    metrics = scores[name]
                    record = {k: metrics.get(k) for k in fields if k in metrics}
                    record.update(bag=row['bag'], group=row['group'], receiver=receiver, scenario=scenario,
                                  model=name, distance_rmse=v6.metric_value(metrics, 'distance'))
                    writer.writerow(record)


def run_stage(role, ids, output, workers):
    destination = output/role
    destination.mkdir(parents=True, exist_ok=False)
    store = ex.Store()
    bags = store.plan['splits'][role]
    jobs = [(b, role, ids, str(destination)) for b in bags]
    clean, stress, access, identities = [], [], [], []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for bag, data in zip(bags, pool.map(evaluate_bag, jobs)):
            clean.append(data['clean'])
            stress.extend(data['stress'])
            access.extend(data['access'])
            identities.extend(data['baseline_identity'])
            print(role, bag, 'done', flush=True)
    decision, summaries, reasons = gates(clean, stress, ids)
    models = {ALIASES.get(name, name): asdict(c) for name, c in configurations(ids).items()}
    result = dict(role=role, models=models, clean=clean, stress=stress, test_evaluated=False,
                  baseline_identity=identities, source_sha256=verify_sources())
    if role == 'validation':
        result['baseline_reproduction'] = v6.reproduce_published_v5(clean)
    write_new(destination/'results.json', result)
    write_new(destination/'decision_v6_unchanged.json', decision)
    write_new(destination/'summary.json', dict(models=summaries, rejection_reasons=reasons))
    write_new(destination/'access.json', dict(access=access, test_evaluated=False))
    export_csv(destination/'per_bag.csv', clean, stress, ids)
    print(json.dumps(dict(role=role, summaries=summaries, reasons=reasons), ensure_ascii=False), flush=True)
    return summaries, reasons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['development', 'validation'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 2:
        raise ValueError('Use 1 or 2 workers')
    source_hashes = verify_sources()
    output = args.output.resolve()
    plan = json.loads(PLAN.read_text())
    if args.stage == 'development':
        output.mkdir(parents=True, exist_ok=False)
        write_new(output/'STARTED.json', dict(hypothesis='H01', baseline_commit=BASE,
            source_commit=os.environ.get('GITHUB_SHA', subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()),
            source_sha256=source_hashes, python=platform.python_version(), numpy=np.__version__,
            created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), test_evaluated=False))
        ids = [h['id'] for h in plan['variants']]
        summaries, reasons = run_stage('development', ids, output, args.workers)
        safe = [name for name in ids if not [r for r in reasons[name] if r != 'insufficient_gain']]
        if not safe:
            write_new(output/'OUTCOME.json', dict(conclusion=('недостаточно данных' if any('insufficient_reference_data' in r for r in reasons.values()) else 'отвергнута'), stage='development',
                reason='No preregistered candidate passed development nonregression/safety gates',
                rejection_reasons=reasons, validation_evaluated=False, test_evaluated=False, merge_ready=False))
            return
        selected = min(safe, key=lambda name: (summaries[name]['clean_rmse'], ids.index(name)))
        config = asdict(configurations([selected])[selected])
        canonical = json.dumps(config, sort_keys=True, separators=(',', ':')).encode()
        freeze = dict(hypothesis='H01', selected=selected, baseline_commit=BASE,
            config=config, config_sha256=hashlib.sha256(canonical).hexdigest(), source_sha256=source_hashes,
            development_results_sha256=ev.sha(output/'development/results.json'),
            created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), validation_opened=False,
            test_evaluated=False, immutable=True)
        write_new(output/'FREEZE.json', freeze)
        write_new(output/'selected.json', dict(name=selected, config=config))
        yaml = (ROOT/'src/reserve_odometry/config/adaptive_v5.yaml').read_text().rstrip()+'\n'
        (output/'selected.yaml').write_text(yaml+'    model.h01_projection_gain: '+str(config['h01_projection_gain'])+'\n')
        print('FROZEN before validation:', selected, freeze['config_sha256'], flush=True)
    else:
        freeze = json.loads((output/'FREEZE.json').read_text())
        if freeze['source_sha256'] != source_hashes:
            raise ValueError('Source changed after development freeze')
        if freeze['development_results_sha256'] != ev.sha(output/'development/results.json'):
            raise ValueError('Development evidence changed after freeze')
        selected = freeze['selected']
        config = asdict(configurations([selected])[selected])
        if config != freeze['config'] or hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':')).encode()).hexdigest() != freeze['config_sha256']:
            raise ValueError('Candidate changed after freeze')
        _, reasons = run_stage('validation', [selected], output, args.workers)
        # Accuracy pass alone is not full runtime acceptance.
        passed = not reasons[selected]
        write_new(output/'OUTCOME.json', dict(conclusion='недостаточно данных' if passed else 'отвергнута',
            stage='validation', selected=selected, accuracy_gates_passed=passed,
            rejection_reasons=reasons[selected], validation_evaluated=True, test_evaluated=False,
            runtime_status='requires separate candidate ROS/resource/latency evidence', merge_ready=False,
            limitation='Reused validation is not an independent final test'))


if __name__ == '__main__':
    main()
