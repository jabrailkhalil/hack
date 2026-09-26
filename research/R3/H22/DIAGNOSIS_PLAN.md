# R3-H22: baseline-only premise probe (before fitting PLAN)

Baseline e3b0c9c039d2953fbfcda51231263d38ef9f1024, champion_v8 YAML, actual GuardedReadoutObserver. No fitted candidate exists yet. This stage opens all 64 train bags, only the 3 vehicle topics, never train GNSS/development/validation/test. It does not optimize any coefficient.

Inherited H16 window rule: source grid 20 Hz, 5 s causal warmup and 5 s forecast, anchors after 10 s, fresh/legal controller and fresh agreeing wheels (difference <=0.15 m/s; mean 0.5..35 m/s) throughout. Select the temporal median eligible anchor in each of traction/coast/braking per bag, maximum three windows. Selection is input-only, never based on error. Phase is controller at anchor, not a claim that the whole window has constant command.

Train groups are sorted by the original linked group ID; positions 0,4,8,... are check, all others fitting (exactly H16 rule). Check IDs: 0448e10aab8a0e05, 1e811c142a49aa16, 4ca08ed0da0cb611, 8232b134be2a5002, 96d0ec5b7ee50e7e, bf69dbfe85be52b0, e894436afa9dd9f1. They may be used for post-fit selection but never solver residuals.

Measure v-pred minus held-wheel proxy at 0.5/2/5 s and trapezoidal prefix integrals from anchor to each horizon. Every theta (here only baseline) starts from causal warmup. Recursive velocity drives resistance; no teacher forcing. Preserve initial readout correction until held-wheel expiry and compare the full 101-point forecast to canonical runtime, tolerance 1e-10 m/s. The proxy is not independent truth.

Prerequisite coverage: >=8 fitting groups/30 windows, >=3 check groups/9 windows, >=5 windows of every phase. A potentially addressable prefix-bias defect requires >=20 windows with |e_s(5)|>=0.10 m in >=3 source groups. Count these as potentially affected windows, not useful interventions or accuracy gain. Record all missing groups/phases, per-window errors and group/phase signed biases. If premise/coverage insufficient: INCONCLUSIVE without fitting/validation. Do not change these thresholds after diagnosis.

After this baseline-only probe, publish the complete PLAN BEFORE comparing A/B: fixed dimensionless velocity and integral scales, both objectives, bounds/gauge, one start each, max_nfev80 each, <=1600 actual residual calls total including finite-difference calls, exact train-check selection and R3 development admission. No validation from this workflow; no H23, guard/readout/adaptation changes, main writes, merge or auto-merge.

Source helpers adapt H16 data/recurrence (9b382e352ea6037a71182bedd98bbc34c4b3098f) while pinning full v8 and retaining initial readout for prefix integrals. Immutable runtime/evaluator files are compared against the fixed git commit before IO; generated manifests are evidence, not replacements for historical pins.
