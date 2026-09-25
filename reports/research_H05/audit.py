"""Post-run descriptive audit of immutable H05 evidence; never replays or fits.

Usage: python audit.py --evidence /path/to/extracted/H05 --output /tmp/new-audit
The official verdict remains decision_v6_unchanged.json / H05_contract.json.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics

BASE = 'v5_adaptive_05s'
CANDIDATE = 'H05_ttl2s'
RESULTS_SHA256 = 'b3a8dc92ce494fb8e557d860ed6430b5fa33ccdfe100dd9804530e2d7a0dbd19'
DISPLAY_EPS = 1e-10  # Descriptive listing only, never an acceptance threshold.


def load(path):
    return json.loads(path.read_text())


def change(a, b):
    return (a / b - 1) * 100 if a is not None and b not in (None, 0) else None


def value(scores, key):
    if key == 'distance':
        return scores.get('distance_surrogate', {}).get('reanchored_span_rmse_m')
    if key == 'absolute_bias':
        v = scores.get('bias')
        return abs(v) if v is not None else None
    return scores.get(key)


def group_macro(rows, model, key):
    groups = {}
    for row in rows:
        for scores in row['receivers'].values():
            v = value(scores[model], key)
            if v is not None:
                groups.setdefault(row['group'], []).append(v)
    return statistics.mean(statistics.mean(v) for v in groups.values()) if groups else None


def write_csv(path, rows, columns):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    raw = args.evidence / 'validation/results.json'
    if hashlib.sha256(raw.read_bytes()).hexdigest() != RESULTS_SHA256:
        raise ValueError('Not the original H05 run results')
    r = load(raw)
    if r['test_evaluated'] or r['source_ref'] != '613907b067513c65a36dc8a2cc79ce19858b01b9':
        raise ValueError('Unexpected source or data access')
    args.output.mkdir(parents=True, exist_ok=False)
    regressions, diagnostics, per_bag = [], [], []
    equal_coverage = True
    clean_worse = 0
    recovery_deltas, event_deltas = [], []
    for scope in ('clean', 'stress'):
        for row in r[scope]:
            for receiver, scores in row['receivers'].items():
                b, a = scores[BASE], scores[CANDIDATE]
                equal_coverage &= a['n'] == b['n'] and a['coverage'] == b['coverage']
                if scope == 'clean' and b['rmse'] is not None:
                    clean_worse += int(a['rmse'] > b['rmse'])
                for key in ('rmse', 'mae', 'p95', 'absolute_bias', 'distance', 'event_rmse', 'recovery_s'):
                    av, bv = value(a, key), value(b, key)
                    if av is None or bv is None:
                        continue
                    if key == 'recovery_s': recovery_deltas.append(av-bv)
                    if key == 'event_rmse': event_deltas.append(av-bv)
                    if av-bv > DISPLAY_EPS:
                        fault = row.get('fault', {})
                        regressions.append(dict(scope=scope, bag=row['bag'], receiver=receiver,
                            fault_kind=fault.get('kind'), fault_start=fault.get('start'), fault_end=fault.get('end'),
                            metric=key, baseline=bv, candidate=av, absolute_delta=av-bv,
                            change_percent=change(av, bv)))
        for key in ('rmse', 'mae', 'p95', 'absolute_bias'):
            b, a = (group_macro(r[scope], m, key) for m in (BASE, CANDIDATE))
            diagnostics.append(dict(scope=scope, metric=key, baseline=b, candidate=a, change_percent=change(a,b)))
    for row in r['clean']:
        pairs = [s for s in row['receivers'].values() if s[BASE]['rmse'] is not None]
        b, a = (statistics.mean(s[m]['rmse'] for s in pairs) if pairs else None for m in (BASE, CANDIDATE))
        per_bag.append(dict(bag=row['bag'], group=row['group'], receivers_with_reference=len(pairs),
                           baseline_clean_rmse=b, candidate_clean_rmse=a, change_percent=change(a,b)))
    test_counts = {}
    for name in ('baseline-unit', 'patched-core-unit', 'patched-timeline-unit', 'H05-unit'):
        text = (args.evidence / (name + '.log')).read_text()
        test_counts[name] = int(re.search(r'Ran (\d+) tests', text).group(1))
        if not text.rstrip().endswith('OK'):
            raise ValueError('Test log not successful: ' + name)
    access = [entry for stage in ('train','validation')
              for entry in load(args.evidence / stage / 'access.json')['access']]
    causal = {scope: {m: sum(row['runtime'][m]['causal_errors'] for row in r[scope])
                      for m in (BASE,CANDIDATE)} for scope in ('clean','stress')}
    resets = {scope: {m: sum(row['runtime'][m]['resets'] for row in r[scope])
                      for m in (BASE,CANDIDATE)} for scope in ('clean','stress')}
    result = dict(description='Post-run descriptive audit; no fitting, no changed evaluator or acceptance gates',
        source_results_sha256=RESULTS_SHA256, run_id=36175046669, run_attempt=1,
        candidate_commit=r['source_ref'], evidence_commit='8c337e8d83504c62899350f5ccfe3725bf6d0779',
        official_decision=load(args.evidence/'validation/decision_v6_unchanged.json'),
        official_contract=load(args.evidence/'validation/H05_contract.json'),
        test_counts=test_counts, per_bag_summary_definition='Mean of available receivers; descriptive only, not official aggregation',
        all_coverage_identical=equal_coverage, clean_bag_receiver_rmse_regressions=clean_worse,
        recovery_comparisons=len(recovery_deltas), max_absolute_recovery_delta_s=max(map(abs,recovery_deltas)),
        max_absolute_event_rmse_delta=max(map(abs,event_deltas)), causal_errors=causal, resets=resets,
        data_access_counts={role:sum(x['purpose']==role for x in access) for role in ('train','validation','test')},
        descriptive_group_macros=diagnostics, regressions_listing_epsilon=DISPLAY_EPS,
        regressions_listed=len(regressions))
    (args.output/'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    write_csv(args.output/'per_bag_summary.csv', per_bag, list(per_bag[0]))
    write_csv(args.output/'regressions.csv', regressions, list(regressions[0]))
    print(json.dumps(dict(test_counts=test_counts, clean_bag_receiver_rmse_regressions=clean_worse,
                         recovery_comparisons=len(recovery_deltas), regressions_listed=len(regressions))))


if __name__ == '__main__': main()
