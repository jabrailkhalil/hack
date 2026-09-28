# R3-H22: sources and limits of verification

## Primary methodological motivation

M. Farina and L. Piroddi, Simulation error minimization identification based on multi-stage prediction, International Journal of Adaptive Control and Signal Processing 25(5), 389-406 (2011), online25August2010. DOI10.1002/acs.1203. Publisher: https://onlinelibrary.wiley.com/doi/10.1002/acs.1203 . Read publisher metadata and abstract through web search; direct page fetch returned403. Full article and proofs were NOT read. The abstract motivates long-horizon prediction/simulation loss instead of assuming a good one-step fit generalizes. It does not establish the proposed prefix penalty, our loss weights, safety of v8, or a real-data improvement.

Consensus and Scite were NOT retried: the task and H16 report document monthly quota stops. No quota workaround, paid article or extra search budget was used. There is no new Consensus fetch card or Scite citation-context validation to claim.

## Project evidence read

Immutable H16 report https://github.com/jabrailkhalil/hack/blob/476ffef5d4135377dc0215572cdabed520b6acfa/reports/research_R2/H16/H16-36184448864-1/REPORT.md ; source9b382e352ea6037a71182bedd98bbc34c4b3098f. H16 full measured-source artifact downloaded and SHA256 checked (f23c013585e40a0b9ac6e1333556fa6a9abea5186c857ae430989ec2e107c548). Used for the causal window/recurrence implementation and negative-result context, not a third selectable fit or causal ablation. Its v7 measurements are not v8 baseline measurements.

Full fixed-v8 runtime/profile/launch/adapter, original scorer/matching/aggregation/split/guards/H11 code were read from the exact baseline source archive; protected bytes match git snapshot. Low-speed input-only construction checked in tools/research_lock/low_speed.py at PR13 source f10e3cfc0689ecbd7894575945897a6696db3e72; only builder conditions copied, applied to genuine development. No other R3 validation result read for selection.

## Executed mathematics

wolfram.wl is the actual Wolfram Language call; wolfram_output.txt includes returned values AND warnings. Results: constant speed bias integrates to b*h; acceleration bias integrates to da*h^2/2; affine error is integrated exactly by trapezoids; normalized speed/prefix quantities dimensionless; common mass/force/power positive scale cancels; gauge-direction sensitivity zero; stable transformed residual squares to rho.

Assumptions are elementary fixed-bias and positive scaling examples, not true vehicle identification assumptions. No claim of global stability of nonlinear switching observer, calibrated covariance, unique physical mass/force identification, or statistical accuracy follows. The Min simplification produced FullSimplify::cas warnings despite returning0; these warnings are retained. Unit ambiguity messages for natural-language second/meter are retained. Local independent numerical tests check rho, trapezoid and full causal rollout parity.
