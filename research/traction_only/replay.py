"""Explicit development-only comparison. Never fits, validates or promotes.

Primary scoring/matching/fault anchors are imported unchanged. Full-bag distance
and retained fault-minus-clean displacement supplement the cropped fault score.
"""
import argparse
from dataclasses import asdict
import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runtime as rt


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rt.verify_pins()
g = load_module('traction_frozen_guarded', rt.ROOT/'tools/research_guarded/compare.py')
v6 = load_module('traction_frozen_v6', rt.ROOT/'tools/research_v6/compare.py')
ev, np, ex = g.ev, g.np, g.ev.ex


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


class DevelopmentStore(ex.Store):
    """Same decoding/units/order as Store; ONLY development payload is allowed."""
    def load(self, bag, purpose='development'):
        row = self.records[bag]
        if purpose != 'development' or row['split'] != 'development' or bag not in self.plan['splits']['development']:
            raise PermissionError('Only the fixed development split is allowed')
        path = self.root/bag/(bag+'_0.db3')
        allowed = list(ex.CHANNELS)+list(ex.REFS)
        if ev.sha(path) != row['sha256']:
            raise ValueError('DB checksum mismatch: '+bag)
        self.access.append({'bag': bag, 'purpose': purpose, 'sha256': row['sha256'], 'topics': allowed})
        events, refs = [], {'master': [], 'rover': []}
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as con:
            query = ('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                     'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic, typ, raw in con.execute(query, allowed):
                stamp, values = ex.decode(raw, typ)
                t = (stamp-row['sensor_start_ns'])/1e9
                if topic in ex.CHANNELS:
                    ch = ex.CHANNELS[topic]
                    events.append((t, ch, float(values[0])/(15 if ch == 0 else 3.6)))
                else:
                    speed = math.hypot(float(values[0]), float(values[1]))
                    if math.isfinite(speed): refs[ex.REFS[topic]].append((t, speed))
        return np.asarray(events, float).reshape(-1, 3), refs


def predictions(events, fault=None):
    arrays, info = {}, {}
    for name, model in rt.models().items():
        arrays[name], info[name] = g.predict(events, model, fault)
    reference = arrays['main']
    for name, a in arrays.items():
        if a.shape != reference.shape or not np.array_equal(a[:, 0], reference[:, 0]):
            raise AssertionError('Schedule mismatch: '+name)
        if info[name]['causal_errors']: raise AssertionError('Future input used')
    if not np.array_equal(arrays['off'], reference, equal_nan=True) or info['off'] != info['main']:
        raise AssertionError('Feature-off mismatch')
    return arrays, info


def score_full(arrays, info, refs):
    receivers = {}
    t = arrays['main'][:, 0]
    for receiver, values in refs.items():
        target = ex.match(values, t)
        scores = {}
        for name, a in arrays.items():
            scores[name] = ex.metrics(t, a[:, 1], target, np.isfinite(target))
            scores[name]['distance_surrogate'] = ev.distance_surrogate(a, target)
            scores[name]['false_stop_samples'] = int(np.sum(np.isfinite(target) & (target > 1) & (a[:, 5] > 0)))
        receivers[receiver] = scores
    return {'receivers': receivers, 'runtime': info, 'outputs': len(t)}


def retained_displacement(clean, faulted, fault):
    """Within-profile fault effect, NOT true XYZ error or a reset of position."""
    result = {}
    for name, a in faulted.items():
        c = clean[name]
        if len(a) == 0:
            result[name] = None
            continue
        j = np.searchsorted(c[:, 0], a[:, 0])
        if np.any(j >= len(c)) or not np.array_equal(c[j, 0], a[:, 0]):
            raise AssertionError('Clean/faulted output times are not comparable')
        before = a[:, 0] < fault['start']
        if not np.array_equal(a[before, :3], c[j][before, :3]):
            raise AssertionError('Fault changed its own strict prefault prefix')
        delta = a[:, 2]-c[j, 2]
        velocity_delta = a[:, 1]-c[j, 1]
        integral = np.r_[0., np.cumsum(.5*(velocity_delta[:-1]+velocity_delta[1:])*np.diff(a[:, 0]))]
        error = float(np.max(np.abs(delta-delta[0]-integral)))
        if error > 1e-7: raise AssertionError('Published distance integral mismatch')
        end10 = np.searchsorted(a[:, 0], fault['end']+10., side='right')-1
        covered = len(a) > 0 and a[-1, 0] >= fault['end']+10.
        result[name] = {'terminal_delta_s_m': float(delta[-1]),
                        'end_plus_10_delta_s_m': float(delta[end10]) if covered and end10 >= 0 else None,
                        'max_integral_identity_error_m': error}
    return result


def run(data_root, output):
    pins = rt.verify_pins()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    store = DevelopmentStore(data_root)
    bags = store.plan['splits']['development']
    if len(bags) != 17: raise ValueError('Development membership changed')
    sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(rt.HERE.iterdir()) if p.is_file()}
    save(output/'started.json', {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'role': 'development', 'python': platform.python_version(), 'numpy': np.__version__,
        'baseline_pins': pins, 'research_sha256': sources, 'models': rt.model_manifest(),
        'fitting_calls': 0, 'validation_opened': False, 'final_test_opened': False})
    clean_rows, cropped_rows, full_rows = [], [], []
    for bag in bags:
        events, refs = store.load(bag)
        save(output/'access.json', store.access)
        metadata = {'bag': bag, 'group': store.records[bag]['group']}
        arrays, info = predictions(events)
        clean = dict(metadata, **score_full(arrays, info, refs))
        # Independent invocation of the unchanged comparator checks our clean adapter.
        if clean['receivers'] != g.compare(events, refs, rt.models())['receivers']:
            raise AssertionError('Clean scoring adapter drift')
        clean_rows.append(clean)
        cropped, full = [], []
        for i, (fault, window) in enumerate(g.fault_windows(events)):
            # The original crop and full trajectory each warm up under their OWN config.
            row = dict(metadata, fault=fault, **g.compare(window, refs, rt.models(), fault))
            cropped.append(row); cropped_rows.append(row)
            changed, diagnostics = predictions(events, fault)
            row = dict(metadata, fault=fault, **score_full(changed, diagnostics, refs),
                       retained=retained_displacement(arrays, changed, fault))
            full.append(row); full_rows.append(row)
            np.savez_compressed(output/f'{bag}-fault-{i}.npz', **changed)
        np.savez_compressed(output/f'{bag}-clean.npz', **arrays)
        save(output/f'{bag}.json', {'clean': clean, 'cropped': cropped, 'full': full})
        print(bag, 'original faults', len(cropped), flush=True)
    summary = {name: v6.summary(clean_rows, cropped_rows, name) for name in rt.NAMES}
    for name in rt.NAMES: summary[name]['full_faulted_distance_rmse'] = v6.macro(full_rows, name, 'distance')
    expected = {'clean_rmse': .09266814298282507, 'fault_rmse': .2375486120563008,
                'pooled_rmse': .1293056944774334, 'distance_rmse': 5.310295004801444, 'samples': 394221}
    baseline = summary['main']
    for key, value in expected.items():
        if not math.isclose(baseline[key], value, rel_tol=1e-10, abs_tol=1e-12):
            raise AssertionError('Baseline fingerprint mismatch: '+key)
    save(output/'summary.json', {'models': summary, 'baseline_fingerprint': 'PASS',
        'status': 'DEVELOPMENT_PRIMARY_ONLY', 'ready_to_merge': False,
        'remaining': ['low-speed and abrupt/slow common-mode suites',
                      'per-group and individual safety gates / train-check',
                      'separately frozen validation only after admission', 'enabled installed ROS verification']})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-development', action='store_true', help='Explicitly authorize ONLY development measurement IO')
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.run_development:
        if args.data_root is None or args.output is None: parser.error('--data-root and --output required')
        print(json.dumps(run(args.data_root, args.output), indent=2, allow_nan=False))
    else:
        rt.verify_pins()
        print(json.dumps({'status': 'PREPARED_NOT_EVALUATED', 'models': rt.model_manifest()}, indent=2))
