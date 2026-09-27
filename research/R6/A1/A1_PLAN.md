# R6-A1 independent causal re-audit; no production fix

Baseline b2783206000091ab11a1c11ac3ff79082188a4fb, tree
973d50d288e050325ee1c71a90fa8d81f2a099af. Full champion_v8.yaml and unchanged
GuardedReadoutObserver/Timeline,20Hz/delay0. Branch research/R6-A1-recovery-causality.
Prior safety-lineage A1 is historical evidence, not a result to overwrite.
H52/H58/H59/H60 and all previous reports remain unchanged.

One locked previously identified train-check bag 30639_0be558e2, group
0d4506540f0e7621, event08f850870ac08fb7707e, both dropout [71.55,74.55).
Verify A0 ZIP/receipt/all payload hashes and exact canonical source tree before
replay. Decode only controller/front/rear, SQL timestamp/id arrival order,
original source stamps and units. Require exact event array hash and exact A0
archived t/v/s and clean v/s; independently check signed integral identity,
finite/bounded dt, no reset, post-fault accumulation. Failure blocks all oracles.
No GNSS/teacher or other measurement DBs are used.

Returning evidence: fresh finite in-range agreeing near-zero wheels, skew within
canonical pair_skew; source stamps after fault; fresh command <=deadband;
>=2 distinct pairs spanning canonical reacquire_dwell0.8s; evidence gaps >2max_age
restart. Inspect per-channel new stamps, candidate rate/range outcomes and actual
injection schedule. Held duplicate samples may support continuity but cannot be
new assimilation evidence. A simultaneously locked physical pair remains
unidentifiable from these three inputs; classify RETURNING_PAIR_AMBIGUOUS if
independent physical validity is unavailable. Oracles then have explicitly
conditional meaning: test accepting observationally qualified raw pairs, not
assert that actual tram speed is zero. No runtime accept-all-zero rule.

A0 canonical; D one d:=0 at first qualified return; Z bypass ONLY zero_pair
rejection at qualified ticks, leave d and ordinary innovation/rate/stop gates
canonical; DZ combines these exact controls. No s reset, coefficients/readout/
Q/R/other intervention. S only if these fail to explain accumulation.
Re-use audited prior forensic driver as a starting point under research/R6/A1,
never production files; verify passive collector vs untouched replay outputs.

For same raw tuple counterfactual, save pre-step canonical and paired-clean
state at the same timestamp, clone, feed identical Sample bytes, compare zero
and ordinary gate outcomes. Neither clone consumes future data. Distinguish
one-wheel ACCEPTED from full pair FUSED and mode STOPPED.

Measure full timeline, +1/5/10/30/60/120/300 horizons and terminal, d, inner and
published v, modes, post-return rejected NEW samples, saturated time, first
accepted/fused/STOPPED; stable recovery requires trusted fusion/stop, no sustained
saturation and zero terminal60s dv/growth (1e-8 numeric equality). No terminal
absolute-distance threshold chosen from observed results. Use final stationary
portion only as an outcome, not as intervention input.

Necessary/sufficient statements are restricted to this event and controls:
removing D abolishing runaway supports contextual necessity of retained D on
this path; it does not prove D alone universally sufficient. Similarly Z. If
either individual cut restores recovery, do not claim that only combined DZ
works. If both work, report both sufficient interventions and neither residual
factor alone sustaining runaway under the tested intervention. Single required
verdict uses ZERO_REACQUISITION when Z restores acceptance AND same-raw self-lock
is established (D may also be sufficient); otherwise DISTURBANCE if D works,
COUPLED only if neither individual works but DZ works, else NOT_CONFIRMED.
This tie policy is fixed before this re-audit and not a dominance ranking.

Alternative audit: timestamp/dt/duplicates/future/overflow/nonfinite/integral/
reset/readout/injection end/clean pairing/saturation logging/no future CF.
Infrastructure risk TRUE only for proven infrastructure defect, not runtime bug.
No B01 implementation, no sweep, no refit, no development/validation/final/test.
Publish separate new checkpoint/export in existing A1 workspace, with existing
A1 artifacts preserved. STOP after causal verdict and one mechanism proposal.
