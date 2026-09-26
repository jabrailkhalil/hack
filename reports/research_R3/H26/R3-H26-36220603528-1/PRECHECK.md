# R3-H26: prospective foundation check

Baseline e3b0c9c039d2953fbfcda51231263d38ef9f1024; canonical GuardedReadoutObserver, champion_v8.yaml, all model/readout fields loaded from that exact profile. Original runtime/scorer/split unchanged. This is a train-only diagnostic protocol, not a fitted candidate or a validation freeze. No measurement payload has been opened for H26 before this document.

## Question and stop rule

A serially correlated innovation is not automatically serially correlated measurement error. Before changing the filter, test whether positive short-lag correlation survives causal controls for timestamp age, controller transitions and model mismatch, consistently across independent source groups. If it disappears, is unstable between groups, or cannot be separated from dynamic mismatch, report INCONCLUSIVE; do not build/promote a candidate solely to obtain a result.

## Data and immutable controls

Only original train vehicle topics for this check; no train GNSS, validation or final/test SQL IO. All 64 train bags retained, missing/short sequences reported rather than scored as zero. Use groups from split_v3.json; deterministic fitting/check partition: sort train group IDs by SHA256('R3-H26:'+group), every fourth (indices 0,4,...) is check; all other groups fitting. Related bags stay together. Duplicate bag bytes do not imply extra independent groups. Group-balanced fitting and diagnostics, never tick-level significance.

Use a passive subclass to capture each genuine FUSED update without modifying any baseline state or returned Estimate. Retain raw innovation z-v_prior, model acceleration, sample mean age/skew, controller, drive lag, old disturbance and prior trusted wheel acceleration mismatch. No observer update from held duplicates. Verify subclass vs separately constructed canonical v8 on a full real train bag before making claims, including every baseline state field, published outputs and unchanged official scorer using its train-no-reference behavior. Real reference baseline sanity, if proceeding, uses only development.

## Trusted and controlled samples

Record only two new accepted agreeing wheels with abs(front-rear)<=0.15 m/s, abs(z)>0.5 m/s, nonstale command, abs(raw innovation)<=3*wheel_sigma. FUSED alone is not independent evidence of correctness. Segments break on invalid/rejected held pair or >max_age_s between recorded updates. Primary adjacent-correlation pairs require 0.08<=delta pair stamp<=0.12 s; do not bridge missing updates.

Raw and age-adjusted residuals (e_age=e+a_model*mean_age) are reported separately; age adjustment is DIAGNOSTIC ONLY and never enters the baseline. Steady subset requires >=2 source seconds of healthy evidence, controller range over previous 2 s<=0.02, and abs(drive_target-drive_a)<=0.1 m/s^2. Exclude near-stop points abs(z)<=0.5. Tight-dynamics subset additionally abs(previous trusted wheel acceleration-current model acceleration)<=0.2 m/s^2; previous wheel derivative is causal and must have gap<=max_age_s. This control can absorb genuine colored error as well as model mismatch; disappearing correlation therefore means INCONCLUSIVE, not white-noise proof.

Fit exactly one fixed ridge linear diagnostic nuisance model for e_age on fitting groups only. Features, with fixed scales: intercept; command u; predicted v/40; model a/3; (target-drive_a)/3; old d/0.6; previous wheel-a minus model-a divided by 3; mean_age/0.25; abs(skew)/0.1. Ridge=1e-3 on nonintercept coefficients; group weights sum equally; no lagged innovation regressor. Apply frozen coefficients unchanged to check groups. This is NOT reidentification of runtime physics. Report before/after residual RMS and lag-1 correlation for all trusted, steady and tight-dynamics subsets, per bag and original group. Center within each diagnostic group; no use of check means in the fitted predictor.

## Prespecified sufficient basis

For the tight controlled check subset require >=3 original check groups, each >=200 usable adjacent pairs, >=1000 pairs overall. At least two-thirds of qualifying check groups must have lag-1 correlation>=0.10 and residual RMS>=0.01 m/s, and their median correlation must be>=0.10. Require the median controlled correlation to retain at least half the positive age-adjusted steady correlation (otherwise strong confounding), and no sign reversal of median fitting vs check correlation. Failing this basis gives INCONCLUSIVE, not REJECTED accuracy. Counts of probes are potential observation coverage, not count of changed outputs; unchanged passive probe has zero interventions by construction.

## Conditional single AR(1) and limits

Only after sufficient basis, publish full PLAN before comparing algorithms. Exactly one b_next=rho*b+eta, z=v+b+epsilon model with covariance [v,b], rho in [0,0.9], one group-balanced offline likelihood start and <=60 actual objective calls (including finite-difference calls). No extra grid or restarts. Separate legacy d mean/adaptation, total stationary measurement variance>=wheel_sigma^2, abs(b)<=3*wheel_sigma. Actual effective velocity gain must reach guarded readout through an explicit hook; scalar gain reconstruction cannot be assumed valid. Feature-off exact canonical v8 and separately specified white limit required. All hard gates/zero-lock/quarantine preserved.

No development or validation candidate evaluation if foundation is insufficient. If foundation passes, prospective development admission remains >=2% clean or >=5% original fault gain; clean/fault/pooled regression<=0.5%, distance<=1%, per-bag clean<=baseline+max(0.005,5%); equal masks/coverage; no new false stops/individual unrecovered/causal/reset errors; original low-speed and abrupt-common suites <=0.5% event regression. Only then publish freeze before one validation. Final test forbidden.

Literature scope: supplied DOI 10.1016/j.cam.2022.114138, distinguish abstract/full text. Known Consensus/Scite quota stops will not be retried. Independent local symbolic/numeric math checks may substitute Wolfram. No article purchase or paid compute.
