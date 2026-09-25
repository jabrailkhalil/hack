"""Audit saved H06 evidence without reopening data or changing the evaluator."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

BASE = 'v5_adaptive_05s'
CANDIDATE = 'H06_evidence_04s_15x'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.evidence
    data = json.loads((root / 'validation/results.json').read_text())
    freeze = json.loads((root / 'candidate-freeze.json').read_text())
    started = json.loads((root / 'validation/started.json').read_text())
    if freeze != started:
        raise AssertionError('Freeze changed before validation')
    differences = []
    stats = {}
    for section in ('clean', 'stress'):
        modes = {name: Counter() for name in (BASE, CANDIDATE)}
        numeric_comparisons = 0
        references = 0
        for row in data[section]:
            for name in modes:
                modes[name].update(row['runtime'][name]['mode_counts'])
            if row['runtime'][BASE] != row['runtime'][CANDIDATE]:
                differences.append([section, row['bag'], 'runtime'])
            for receiver, scores in row['receivers'].items():
                a, b = scores[BASE], scores[CANDIDATE]
                if b.get('event_rmse' if section == 'stress' else 'rmse') is not None:
                    references += 1
                # Baseline has additional common_front/mean_scaled metrics.
                # Compare EVERY field that the evaluator produces for H06.
                for field, value in b.items():
                    if isinstance(value, (int, float)):
                        numeric_comparisons += 1
                    if value != a.get(field):
                        differences.append([section, row['bag'], receiver, field, a.get(field), value])
        stats[section] = dict(bags_or_scenarios=len(data[section]),
            comparisons_with_reference=references,
            numeric_top_level_fields_compared=numeric_comparisons,
            modes={name: dict(counts) for name, counts in modes.items()})
    result = dict(source_commit=data['source_commit'],
        raw_results_sha256=hashlib.sha256((root/'validation/results.json').read_bytes()).hexdigest(),
        freeze_matches_started=True, baseline_reproduction=data['baseline_reproduction'],
        scopes=stats, differences=differences,
        interpretation='No REACQUIRING output in either model; efficacy of recovery policy was not exercised by this fixed suite. No parameter tuning or new measurement IO.')
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
