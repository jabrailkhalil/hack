# H47 checkpoint: DEPENDENCY_PENDING / NOT_EVALUATED

This is a passive feature/offline-label interface, **not** an implemented or fitted reliability intervention. Canonical src, packaging, gates, readout and evaluator are unchanged. No teacher/atlas payload, classifier coefficients, fitted threshold, development scores or successful dependency lock is included.

## Executed checks

From the verified baseline with this directory added:

```bash
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/R5/H47/tests -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m compileall -q src research/R5/H47
```

Special tests are synthetic: prefix invariance, strict source-time checks, history bounds/exclusion of current sample, channel permutation, native state/Estimate equality, OOD abstention, teacher labels offline only, missing dependency/no overwrite checks. The 2500-tick paired synthetic stream is not a real bag benchmark. The collector works from `CausalFeatureProbe(config, readout=readout)`; exact v8 profile loading is shown in tests. It always returns the canonical Estimate. No ROS launch includes it.

## Exact next stage, after the two component archives arrive

Use the already supplied wave2 launch package, not a new teacher implementation. Source PLAN and candidate budget remain fixed. The ordinary dataset ZIP alone does not replace either component.

```bash
python /path/R5_wave2_H44-H48/tools/precheck_components.py \
  --teacher-zip /path/R5_H42_teacher_component.zip \
  --atlas-zip /path/R5_H43_atlas_handoff.zip \
  --extract-to /new/R5-inputs --receipt /new/components.transport.json
```

Read `component_root` for each producer from the actual transport receipt. In the teacher component root:

```bash
python verify_handoff.py . \
  --expected-handoff-sha 5c8129133758bbb715f2e170122b976f95d0240c18daa731472d910f0bf274d0 \
  --lock /new/teacher.native.lock.json
```

In the atlas component root:

```bash
python scripts/verify_handoff.py R5_HANDOFF.json --kind atlas \
  --folds TRAIN_FOLDS.json --output-lock /new/atlas.native.lock.json
```

Then run `tools/verify_folds_bridge.py` from the launch bundle using the **actual** folds paths declared by both manifests and the unchanged canonical `contracts/TRAIN_FOLDS.json`. Read that CLI's `--help`; do not guess file locations or replace producer folds with coordinator copies. Create the full combined `DEPENDENCIES.lock.json` only after these native checks and the bridge, binding teacher policy/reference contract as specified in PLAN. This pending checkpoint has not implemented a successful combined-lock builder; it must not be mistaken for that verification.

Only then evaluate real natural fault-label coverage on fit/check; at least 3/2 qualified source groups required. Do not fit from atlas errors. Do not generate a new H42/H43 handoff to bypass missing bytes. This checkpoint intentionally contains no training/development/validation CLI. Their implementation after dependencies/foundation is the next permitted stage, not a command claimed to exist already.

`dependency_status.py` creates a read-only status receipt and always exits nonzero: even matching ZIP hashes alone do not authorize fitting. It never writes a dependency lock. It has been exercised with absent components and synthetic mismatches, not with the real 85+53 producer payloads.

## Evidence scope

Dataset archive SHA was verified without decoding measurements in this H47 pass. No fitting, H47 train/check example coverage, real H47 replay, enabled ROS, latency/RSS, new Actions or validation/test. No gain or regression numbers are available. General module import and local tests do not change this.

Wolfram explicit symbolic code/output are retained in science/. Automatic semantic-context results were not used as mathematical evidence because they misparsed the symbols. The formula checks concern scalar covariance/logistic curvature only, not physical truth or full observer stability.
