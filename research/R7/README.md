# R7 infrastructure

This branch contains research-only coordination helpers for the R7 architecture wave.
It does not modify the canonical runtime, launch, scorer, or champion_v8 profile.

Pinned runtime baseline:
- commit: b2783206000091ab11a1c11ac3ff79082188a4fb
- tree: 973d50d288e050325ee1c71a90fa8d81f2a099af

R7 tasks:
- A0: oracle headroom audit over already frozen development predictions.
- A1: causal robust moving-horizon estimator (MHE) versus canonical v8 using the same allowed runtime signals.

Before expensive work:
1. Read the R7 Drive Common Contract and task prompt.
2. Atomically claim the task via claims/R7-A0 or claims/R7-A1.
3. Download exact artifacts by Drive ID and verify SHA-256.
4. Create INPUTS.local.json with local paths.
5. Run:
   python research/R7/preflight.py --task A0 --inputs INPUTS.local.json --output DEPENDENCIES.lock
   or:
   python research/R7/preflight.py --task A1 --inputs INPUTS.local.json --output DEPENDENCIES.lock
6. Create and commit the task PLAN before scientific measurement.

Do not treat this infrastructure branch as an accuracy candidate.
Do not merge it to main as part of a candidate result.
