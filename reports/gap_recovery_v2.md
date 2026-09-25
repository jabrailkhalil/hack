# Gap/recovery hypothesis v2

Source commit: `4ebb11ffe836d283c63433c0021b0e7ff1971e64`

GitHub Actions: https://github.com/jabrailkhalil/hack/actions/runs/36137934829

Hypothesis: forward timestamp gaps should be propagated causally instead of resetting relative position; a persistent, mutually agreeing wheel pair should be allowed a bounded reacquisition path after model divergence without accepting short common-mode spikes or zero-locked wheels.

Observed on the fixed 8-bag development smoke set:

- forward clock resets: **0 in all 8 bags**;
- 13 master/rover RMSE comparisons available;
- observer RMSE improved in **9/13** comparisons relative to the previous implementation;
- mean unweighted RMSE delta: **-0.0015146 m/s**;
- largest improvement: 30639_c31df386 rover, **0.07827 -> 0.07135 m/s**;
- largest regression: 30639_e4379d7f rover, **0.14238 -> 0.14257 m/s**;
- 30618_0652866c master: mean wheels **0.04762 m/s**, observer **0.04240 m/s**.

This is a development smoke result, not held-out evidence. The real-bag run did not enter REACQUIRING; that path is covered by synthetic fault tests. GNSS remains evaluator-only.
