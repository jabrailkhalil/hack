# R3-H24 PLAN — before fitting or candidate comparisons

Round R3-v8-fixed. Baseline e3b0c9c039d2953fbfcda51231263d38ef9f1024:
GuardedReadoutObserver + champion_v8.yaml, guarded_odometry_node; returned
Estimate.v/s, 20 Hz/delay0, readout1/holdoff.5, adaptation_tau.5,
wheel_time_compensation0, common_mode_quarantine1.5. No moving main.

## Prior work and measured premise

Read H07/PR22, H17/PR30 (d1e3517 report, ed62dc6 measured source), and
H16/PR34 (476ffef report, 9b382e3 measured source), core/readout/Timeline,
canonical profile/launch, original evaluator, split and v8 safety extensions.
These studies concern response time or multiple physical coefficients; H24
changes only static normalized command amplitude. Proxy improvement alone and
specialized-suite gains do not authorize validation. Long coast/side regressions
must remain visible.

Train-only preflight source 23bd3bc06496dc9deea5b50a4ee8498737ec4c29,
run36220067112/1, artifact10898348614; ZIP SHA256
4d1f0473ce166a210446f54affb87ea4845cea9664c1b133c507e57850f58c06.
All64 train bags yielded 1370779 output ticks, no future-use. The preregistered
amplitude gate in PREFLIGHT.md passed for all6 internal nodes. Each node has
>=17 fitting and6 check groups with >=5s support; design ranks3/3, at least
6 distinct amplitudes per node. Exposure is not independent sample count.

205 deterministic past-warmup/forecast windows: fitting154 (traction68,
braking69,coast17), check51 (traction24,braking21,coast6). Full20/7 fitting/check
membership is fixed by PREFLIGHT SHA256 group rule and coverage.json, never
changed by target errors. Baseline check .5/2s pseudo-RMSE: traction
.05153695/.16993514, braking .16601165/.81542750, coast .07159667/.30650989 m/s.
FUSED wheel-derived acceleration residual at traction x in[0,.25) has negative
bag-then-group mean in all24 represented groups (macro -.10951950 m/s^2);
traction [.5,.75) positive in22/23 groups (macro +.06047501). This warrants a
static-map experiment but DOES NOT isolate map error from sensor age, actuator
history, disturbance or slip. No GNSS was read and these are not ground truth.

## Scope, mathematics and two variants

x=clip((abs(u)-deadband)/(1-deadband),0,1). Replace only q=x^gamma with linear
interpolation at x=(0,.25,.5,.75,1), q0=0,q4=1. Separate traction/braking
triplets 0<=q1<=q2<=q3<=1. Keep saturation, actuator_tau, resistance, d
adaptation, covariance/velocity correction, all raw/model/stop/recovery gates,
readout, common-mode quarantine and Timeline exactly unchanged. Runtime is one
small immutable table per side and bounded arithmetic, no new inputs/history.
Feature-off calls the original power law, not its tabulated approximation.

Two and only two nonlinear fits: lambda=.1 and1.0, one scipy least_squares
TRF invocation per level, jac=2-point, max_nfev=80, ftol=xtol=gtol=1e-8,
no restarts or post-development modifications. Report actual objective calls
including finite-difference calls. Six free knot ordinates, parameterized by
three fractions a,b,c in[0,1] per side:
q1=a; q2=a+(1-a)b; q3=q2+(1-q2)c. Start at exact prior ordinates x^gamma,
converted to fractions. All six nodes passed coverage. If a future exact repeat
has a coverage/hash mismatch, stop instead of changing fitting dimensions.
No H22 penalty, H17 delay, new physical coefficient or other hypothesis.

Every objective call runs a fresh candidate on the stored5s causal warmup up
to the anchor, then2s command-only forecast. Commands are exposed successively
at their recorded held ticks; no later command informs an earlier state.
Wheel values after anchor are offline targets ONLY, never fed to the rollout.
Evaluate returned v at .5s and2s. sigma_h=.1+.2h m/s (.2/.5), dimensionless
r=(v_pred-mean_held_wheels)/sigma_h. Data loss: mean over horizons, then windows,
then ORIGINAL groups. Smooth robust rho(r)=2(sqrt(1+r^2)-1), implemented by
residual transform sqrt(2)*r/sqrt(sqrt(1+r^2)+1) before group weighting.
Penalty=lambda*mean(((free_q-prior_q)/.25)^2). Normalizations identical forboth.
Full warmup is recalculated per parameter call, not fitted from endpoint.
Checks use only fixed check groups, no refits. Pseudo labels are not truth.

Report no-regularization data loss separately, per-group/phase/horizon errors,
node bounds/saturation and data-only numerical Jacobian singular values (no
regularization rows masquerading as identifiability). The prior table itself
is not feature-off: interpolation bias near deadband is a specific risk.

## Eligibility and selection, fixed before any candidate results

Both fits may be evaluated on all17 original development bags if solver/finite
sanity passes; check loss does not override official development scores.
Natural intervention coverage per candidate: target changes >1e-8 on >=100
ticks in>=3 original groups AND returned v changes >1e-8 on>=100 ticks in>=3
reference-bearing groups. Otherwise INCONCLUSIVE, no validation.

All prospective R3 gates are conjunctive:
- >=2% clean group-macro RMSE gain OR >=5% ORIGINAL fault-event macro gain.
- clean/fault/pooled aggregate regression <=.5%; scalar distance<=1%.
- every clean bag/receiver <=baseline+max(.005m/s,.05*baseline).
- identical output timestamps, reference masks, n/coverage; no new false stops,
  individual unrecovered events, causal errors or unexpected resets.
- unchanged low-speed lock suite and H11 abrupt-common-mode suite must each
  have <=.5% event-macro regression and no new stops/individual unrecovered.
- Side veto: clean traction and braking phase group-macro RMSE each <=baseline
  *1.005 (plus1e-12 absolute tolerance); each side needs reference in>=2groups.
  Report coast separately under same.5% phase-regression veto.
- Counterexample tests: endpoints, monotone/continuous/bounded map, deadband,
  sign switches/reverse braking, force/power crossover, true stop/zero-lock,
  common jump quarantine, no future/duplicate/stale ingestion, feature-off
  exact complete v8 equivalence, finite/bounded states and integrated distance.

Auxiliary phase masks use original held valid controller at each output tick;
they never change original benchmark masks. Missing baseline metrics fail
admission; zero baseline uses absolute1e-12 tolerance, not division by zero.
No bootstrap of millions of ticks; receivers are not independent trips.

Selection among candidates passing ALL gates: smallest original fault macro,
then clean macro, then larger lambda (less flexible). No eligible candidate ->
REJECTED for measured variants or INCONCLUSIVE for absent mechanism coverage.
NO validation on development failure. Do not add variants after this decision.

## Identical measurement and separately named diagnostics

Original score/replay/matching/distance and v6 group aggregation are unmodified.
A new role-checked read-only development adapter/factory is allowed. Before
claims, independently reexecute baseline with official evaluate.score and check
all common numerical fields against the factory driver; all baseline source,
profile, split and bag hashes checked. Feature-off full outputs/state equality.

Original fault anchors/warmups/windows exactly tools/research_guarded/compare.py.
Common suite exactly tools/research_h11/compare.py. Low-speed anchor expression
is copied verbatim from tools/research_lock/low_speed.py at PR13 source
f10e3cfc0689ecbd7894575945897a6696db3e72: first valid agreeing wheel1<v<2,u>=0,
t>max(25,.1*t_end),t<t_end-25; lock3/5s, warmup20s,recovery10s.
Apply those immutable rules to development, not validation.

Additional description only (never substitutes original admission): first
vehicle-selected transition into each traction/coast/braking regime after25s
and before end-25, dropout5s starting .5s after transition, warmup20s,
recovery10s. Report all3 phase-specific suites even if they regress, with
small state traces before/during/after dropout. No anchor chosen by errors.

## Runtime cost, execution, later validation barrier

Original tests+research integrity unchanged. New tests run enabled maps andoff;
compile. Three AB/BA cycles per fitted map (6 baseline+6 candidate replays),
same first development flow,10s warmup+180s measured, threads1. Equal collectors,
separate step CPU/replay CPU/wall and output hashes; process RSS not ROS RSS.

Only after development admission create/publish a separate FREEZE commit with
chosen config/source/evaluator/data hashes BEFORE any validation IO. Then one
paired full original validation; no retuning. Enabled candidate ROS replay in
both clocks,offline2CPU/500000000bytes with latency/RSS/GetParameters/import
hashes required for readiness. On accuracy rejection this costly stage is
NOT_RUN_AFTER_REJECTION. Historical CI only tests canonical v8, not the map.

No final-test payload reading, no historical test metric reuse. No merge,
auto-merge, foreign branch/report/main writes, ACL/secrets/purchases or silent
push validation. Compressed large traces/NPZ only own30-day Actions artifacts;
Git compact REPORT/SUMMARY/configs/metrics/hash manifest. Source/candidate,
freeze(if any), and later report commits are separate. Exact commands/scripts
and failures will be preserved. Known Consensus/Scite quotas are not retried;
DOI10.3182/20110828-6-IT-1002.01589 publisher abstract is mechanism context,
not evidence of our result. Wolfram shape/rank identities do not prove closed-
loop observer stability or physical identifiability.
