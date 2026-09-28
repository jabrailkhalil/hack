"""Post-measurement read-only audit. No replay, fitting, or altered gates.

python reports/research_R2/H20/36185299933-1/audit.py \
  --source-root /path/to/measured-checkout --evidence /path/to/unzipped-evidence
"""
import argparse
from collections import defaultdict
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import mean, median
import sys

p = argparse.ArgumentParser()
p.add_argument('--source-root', type=Path, required=True)
p.add_argument('--evidence', type=Path, required=True)
a = p.parse_args()
root = a.source_root.resolve()
evidence = a.evidence.resolve()
sys.path.insert(0, str(root / 'research/R2/H20'))
spec = importlib.util.spec_from_file_location('h20_measured_driver', root / 'research/R2/H20/run.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
B = driver.BASE
freeze = json.loads((evidence / 'experiment/FREEZE.json').read_text())
for path, expected in freeze['source_hashes'].items():
    actual = hashlib.sha256((root / path).read_bytes()).hexdigest()
    assert actual == expected, path
output = {'source_hashes_verified': len(freeze['source_hashes']), 'stages': {}}
for stage in ('development', 'validation'):
    path = evidence / 'experiment' / stage / 'results.json'
    if not path.exists():
        continue
    r = json.loads(path.read_text())
    names = list(r['provenance']['variants'])
    summaries, reasons, decision = driver.contract(r['clean'], r['stress'], names, stage == 'validation')
    assert summaries == r['summaries'], stage
    assert decision == r['legacy_decision'], stage
    if stage == 'development':
        coverage = driver.coverage_and_safety(r['clean'], r['diagnostic_faults'], names)
        assert coverage == r['coverage']
        for name in names:
            reasons[name] += coverage[name]['safety_reasons'] + r['synthetic']['safety_reasons'][name]
    assert reasons == r['reasons'], stage
    info = {'summaries_exact': True, 'decisions_exact': True, 'bags': len(r['clean']),
            'original_fault_scenarios': len(r['stress']), 'diagnostic_fault_scenarios': len(r['diagnostic_faults']),
            'disabled_full_state_ticks': sum(x['diagnostics'][B]['disabled_full_state_ticks'] for x in r['clean'] + r['stress']),
            'summaries': summaries, 'reasons': reasons, 'clean_group_macro_descriptive': {}}
    for name in [B] + names:
        metrics = {}
        for metric in ('mae', 'bias', 'p95'):
            groups = defaultdict(list)
            for row in r['clean']:
                for scores in row['receivers'].values():
                    value = scores[name].get(metric)
                    if value is not None:
                        groups[row['group']].append(value)
            metrics[metric] = mean(mean(values) for values in groups.values()) if groups else None
        info['clean_group_macro_descriptive'][name] = metrics
    output['stages'][stage] = info
    if stage == 'development':
        # Group averaging is descriptive only; it never replaces the original suite.
        groups = defaultdict(lambda: defaultdict(list))
        for row in r['diagnostic_faults']:
            fault = row['fault']
            key = (fault['phase'], fault['form'], tuple(fault['channels']), fault['amplitude'])
            for scores in row['receivers'].values():
                for name in [B] + names:
                    value = scores[name].get('event_rmse')
                    if value is not None:
                        groups[(key, name)][row['group']].append(value)
        breakdown = []
        for key in sorted({k for k, name in groups}):
            baseline = mean(mean(v) for v in groups[(key, B)].values())
            for name in names:
                values = groups[(key, name)]
                candidate = mean(mean(v) for v in values.values())
                breakdown.append({'phase': key[0], 'form': key[1], 'channels': ','.join(map(str, key[2])),
                                  'amplitude': key[3], 'model': name, 'baseline': baseline, 'candidate': candidate,
                                  'absolute': candidate - baseline,
                                  'percent': 100 * (candidate / baseline - 1) if baseline else None,
                                  'groups': len(values), 'reference_pairs': sum(map(len, values.values()))})
        with (evidence / 'audit-diagnostic-breakdown.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(breakdown[0]))
            writer.writeheader()
            writer.writerows(breakdown)
        cost = json.loads((evidence / 'experiment/development/cost.json').read_text())
        ratios = {}
        for name in names:
            selected = [x for x in cost['rows'] if x['candidate_pair'] == name]
            ratios[name] = {}
            for metric in ('step_cpu_s', 'replay_cpu_s', 'replay_wall_s'):
                pairs = []
                for i in range(6):
                    base = next(x[metric] for x in selected if x['repetition'] == i and x['name'] == B)
                    cand = next(x[metric] for x in selected if x['repetition'] == i and x['name'] == name)
                    pairs.append(cand / base)
                ratios[name][metric] = {'ratios': pairs, 'median_percent': 100 * (median(pairs) - 1)}
        output['cost'] = {'bag': cost['bag'], 'threads': cost['threads'], 'paired_ratios': ratios}
print(json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False))
