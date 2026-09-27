"""H44 stage 0: pinned-v8 development replay only; no training or candidate.

Imports existing scorer, masks, fault construction and group aggregation.
No function in this script reads train/validation/test measurements.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from functools import partial
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import sys
import time
import csv
from interface import ROOT, BASE, TREE, PROFILE, profile
from reserve_odometry.guarded_readout import GuardedReadoutObserver

PLAN_SHA = 'd155cae00b372da5930afe3aee961499fa0e9f76'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


g = module('h44_original_guarded_compare', 'tools/research_guarded/compare.py')
v6 = module('h44_original_v6_compare', 'tools/research_v6/compare.py')
ex, np = g.ev.ex, g.np


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def source_integrity(receipt):
    receipt = json.loads(Path(receipt).read_text())
    if (receipt['source_status'] != 'VERIFIED' or
        receipt['actual_git_tree'] != TREE or
        receipt['baseline_commit_binding'] != BASE or
        receipt['file_count'] != 320):
        raise ValueError('Wrong baseline source receipt')
    for entry in receipt['files']:
        path = ROOT / entry['path']
        if sha(path) != entry['sha256']:
            raise ValueError('Changed baseline bytes: ' + entry['path'])
        mode = '100755' if path.stat().st_mode & 0o111 else '100644'
        if mode != entry['mode']:
            raise ValueError('Changed executable bits: ' + entry['path'])
    return {'checked_files': len(receipt['files']), 'tree': TREE,
            'source_receipt_semantic_sha256': sha_file_receipt(receipt)}


def sha_file_receipt(data):
    # A semantic receipt digest, explicitly not the original file SHA256.
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


class DevelopmentStore(ex.Store):
    """Original decoding/scales/order; development-only check before any IO."""
    def load(self, bag, purpose):
        r = self.records.get(bag)
        if (purpose != 'development' or r is None or r['split'] != 'development' or
            bag not in self.plan['splits']['development']):
            raise PermissionError('Only original development measurements are permitted')
        path = self.root / bag / (bag + '_0.db3')
        if sha(path) != r['sha256']:
            raise ValueError('DB checksum mismatch: ' + bag)
        allowed = list(ex.CHANNELS) + list(ex.REFS)
        events, refs = [], {'master': [], 'rover': []}
        origin = r['sensor_start_ns']
        # Mirror ex.Store.load query exactly; neither global source sorting nor
        # reference filtering is introduced by the role adapter.
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as con:
            query = ('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                     'WHERE t.name IN (' + ','.join('?' for _ in allowed) + ') ORDER BY m.timestamp,m.id')
            for topic, typ, raw in con.execute(query, allowed):
                stamp, values = ex.decode(raw, typ)
                t = (stamp - origin) / 1e9
                if topic in ex.CHANNELS:
                    ch = ex.CHANNELS[topic]
                    events.append((t, ch, float(values[0]) / (15 if ch == 0 else 3.6)))
                else:
                    speed = math.hypot(float(values[0]), float(values[1]))
                    if math.isfinite(speed):
                        refs[ex.REFS[topic]].append((t, speed))
        self.access.append(dict(bag=bag, purpose=purpose, topics=allowed, sha256=r['sha256']))
        return np.asarray(events, float), refs


def worker(args):
    bag, data_root, out = args
    store = DevelopmentStore(data_root)
    events, refs = store.load(bag, 'development')
    cfg, readout, operational = profile()
    if g.OPS != operational:
        raise ValueError('Evaluator operational settings differ')
    model_set = {'main': (partial(GuardedReadoutObserver, readout=readout), cfg)}
    metadata = dict(bag=bag, group=store.records[bag]['group'], role='development')
    clean = dict(**metadata, **g.compare(events, refs, model_set))
    stress = [dict(**metadata, fault=fault, **g.compare(window, refs, model_set, fault))
              for fault, window in g.fault_windows(events)]
    result = dict(clean=clean, stress=stress, access=store.access)
    write(Path(out) / 'bags' / (bag + '.json'), result)
    print('BASELINE_ONLY', bag, 'faults', len(stress), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--source-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2, choices=range(1, 5))
    parser.add_argument('--diagnostic-source-sha', default=None)
    args = parser.parse_args()
    pins = source_integrity(args.source_receipt)
    cfg, output, operational = profile()
    store = DevelopmentStore(args.data_root)
    bags = store.plan['splits']['development']
    if len(bags) != 17 or len({store.records[b]['group'] for b in bags}) != 7:
        raise ValueError('Unexpected development membership')
    args.output.mkdir(parents=True, exist_ok=False)
    provenance = dict(baseline_sha=BASE, baseline_tree=TREE, plan_sha=PLAN_SHA,
        diagnostic_source_sha=args.diagnostic_source_sha, measured_candidate_sha=None,
        module_file=str(Path(sys.modules[GuardedReadoutObserver.__module__].__file__).resolve()),
        observer_class=GuardedReadoutObserver.__name__, config=asdict(cfg), readout=asdict(output),
        operational=operational, source_integrity=pins, receipt_file_sha256=sha(args.source_receipt),
        driver_sha256=sha(__file__), interface_sha256=sha(Path(__file__).with_name('interface.py')),
        versions=dict(python=platform.python_version(), numpy=np.__version__, platform=platform.platform()),
        stage='BASELINE_ONLY_DEVELOPMENT', candidate_implemented=False, optimizer_calls=0,
        dependencies_status='DEPENDENCY_PENDING', train_measurements_opened=False,
        validation_opened=False, test_opened=False)
    write(args.output / 'started.json', provenance)
    begin = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(worker, [(b, args.data_root, args.output) for b in bags]))
    clean = [r['clean'] for r in rows]
    stress = [s for r in rows for s in r['stress']]
    access = [a for r in rows for a in r['access']]
    summary = v6.summary(clean, stress, 'main')
    expected = dict(clean_rmse=.09266814298282507, fault_rmse=.2375486120563008,
                    pooled_rmse=.1293056944774334, distance_rmse=5.310295004801444, samples=394221)
    deltas = {k: summary[k] - expected[k] for k in expected}
    fingerprint = dict(expected=expected, deltas=deltas,
                       passed=all(abs(x) <= 1e-12 for x in deltas.values()))
    result = dict(**provenance, baseline_metrics=summary, candidate_metrics=None,
                  clean=clean, stress=stress, access=access, fingerprint=fingerprint,
                  scientific_verdict='NOT_EVALUATED', accuracy_contract_evaluated=False,
                  elapsed_wall_s=time.perf_counter() - begin)
    write(args.output / 'results.json', result)
    write(args.output / 'access.json', access)
    write(args.output / 'baseline_summary.json', dict(metrics=summary, fingerprint=fingerprint))
    flat = []
    for row in clean + stress:
        f = row.get('fault')
        for receiver, models in row['receivers'].items():
            m = dict(models['main'])
            distance = m.pop('distance_surrogate', {})
            flat.append(dict(bag=row['bag'], group=row['group'], receiver=receiver,
                model='canonical_v8_only', case='clean' if f is None else f['kind'],
                duration_s=None if f is None else f['end']-f['start'], **m,
                distance_rmse_m=distance.get('reanchored_span_rmse_m')))
    with (args.output / 'baseline_per_bag.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, sorted(set().union(*(r.keys() for r in flat))))
        writer.writeheader(); writer.writerows(flat)
    source_integrity(args.source_receipt)
    if not fingerprint['passed']:
        raise RuntimeError('Baseline fingerprint mismatch; inspect preserved evidence')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
