"""Post-validation diagnostic, NOT acceptance data or parameter selection.

One synthetic, known-truth common-mode bias pulse: [2.0, 2.7) seconds, +5 m/s
on both wheels. Model-generated truth, full Observer.step at 20 Hz with held
10 Hz wheel pairs; fixed adaptive_v5 physics from the completed run freeze.
No algorithm/parameter changes are performed by this diagnostic.
"""
import argparse
from dataclasses import asdict
import csv
import json
from pathlib import Path

from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.recovery import RecoveryConfig, RecoveryObserver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    frozen = json.loads(args.freeze.read_text())
    params = frozen['models']['v5_adaptive_05s']
    truth = Observer(Config(**params)); truth.reset(velocity=5.)
    models = {'baseline': Observer(Config(**params)),
              'H06': RecoveryObserver(RecoveryConfig(**params))}
    for observer in models.values():
        observer.reset(velocity=5.)
    rows = []
    pair = None
    for i in range(101):
        t = i * .05
        reference = truth.step(t, Sample(t, 1.))
        if i % 2 == 0:
            fault = 2.0 <= t < 2.7
            pair = Sample(t, reference.v + (5. if fault else 0.))
        for name, observer in models.items():
            estimate = observer.step(t, Sample(t, 1.), pair, pair)
            rows.append(dict(observer=name, t=t, reference_v=reference.v,
                estimate_v=estimate.v, error=estimate.v - reference.v,
                mode=estimate.mode, wheel_stamp=pair.t, wheel_value=pair.value,
                evidence_s=getattr(observer, 'recovery_evidence_s', 0.)))
    with (args.output / 'trace.csv').open('x', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    result = dict(kind='post-validation synthetic diagnostic; not acceptance evidence',
        candidate_runtime_source_commit=frozen['source_commit'],
        fault=dict(kind='common_mode_bias', start_s=2., end_s=2.7, offset_mps=5.),
        model_config=params, output_rate_hz=20., wheel_rate_hz=10., models={})
    for name in models:
        selected = [r for r in rows if r['observer'] == name]
        acquired = [r['t'] for r in selected if r['mode'] == 'REACQUIRING']
        result['models'][name] = dict(first_reacquiring_s=min(acquired) if acquired else None,
            reacquiring_ticks=len(acquired),
            max_abs_error_mps=max(abs(r['error']) for r in selected),
            max_abs_error_during_fault_mps=max(abs(r['error']) for r in selected if 2. <= r['t'] < 2.7))
    (args.output / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
