# R3-H24: train-only preflight before implementation/fitting

Baseline e3b0c9c039d2953fbfcda51231263d38ef9f1024; real GuardedReadoutObserver,
champion_v8.yaml. No candidate, no fitting, no development/validation/test in this stage.
This protocol is published before train IO. The full PLAN will be published after
these diagnostics and before either of the two permitted fits.

All 64 existing train bags, vehicle-only Store. Output ticks use original Timeline
and source stamps. Train groups sorted by SHA256('R3-H24-fit-check:'+group); indices
0 mod 4 are check, all others fitting. Membership is not selected from errors.

Healthy exposure: fresh controller/front/rear, original age/skew/range limits,
front/rear difference <0.15 m/s, mean speed (0.5,35) m/s. Report exposure seconds,
distinct command levels and original groups separately. Wheel-derived two-point
acceleration minus current physical acceleration is summarized by phase/quartile
as a diagnostic only: delayed wheels/disturbance/slip may explain it too.

A node x=.25,.5,.75 per traction/braking can be free only with hat basis >=.1
for >=5s in >=3 fitting and >=2 check groups, >=2 distinct command amplitudes,
and >=20s total exposure. Endpoints fixed. Uncovered nodes remain x^gamma.
The distinct group/amplitude design must have full column rank (tol 1e-8).
Zero free dimension/rank failure -> INCONCLUSIVE without validation or fitting.
These are structural support conditions, not proof of statistical identifiability.

Offline recursive target windows: 5s warmup and 2s forecast on 20Hz held inputs,
all healthy over entire 7s; predictions at .5/2s, average wheel pseudo-target only.
In each bag/phase/quartile select median eligible anchor; per original group/
phase/quartile select median of these bag representatives. Coast has one bin.
Initial state always from past warmup, not the future endpoint. Future commands
are supplied only as they become available at successive forecast ticks, future
wheel values exclusively label offline loss. No warmup state reuse across bags.

This run records no candidate accuracy. It preserves coverage/per-bag/residuals,
compressed window data only in its private Actions artifact (30-day retention).
No raw bags or large traces in Git. No automatic validation workflow.
