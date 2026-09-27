# GNSS availability audit — fixed before this new replay

Parent: 2037ea16fb7a7b2777418ccc8924bdc688e1159d (PR63).
The organizer chat supplied in this turn permits late GNSS but guarantees only
initial availability, without giving a guaranteed duration or later rate.
Previous recorded-input results are already known. The unchanged Localizer needs
course derived from recent fixes; audit this hidden input dependency, not accuracy.

Keep the original maps/grid hypothesis, map algorithm, profiles and raw distance.
Use exact published NPZs from v8_pathgraph_gnss_20260927.zip; this is NOT a fresh
velocity replay. Reprocess position only. Read ONLY rover NavSatFix payloads from
the pinned check-code DB. No localization, reference velocity or reference pose
payload is decoded, and no new RMSE is computed.

Receipt origin: minimum receipt time of the three vehicle input topics and rover
fixes. No reference-based alignment. The masking function sees only receipt time
and schedules, never coordinates, status, course, map distance or scoring errors.
All initial windows are half-open [origin, origin+duration).

Fixed scenarios for both model caches:
- recorded input, exact reproduction of previously published position arrays;
- no GNSS (resilience only, outside the organizer's initial-availability guarantee);
- only the first 1, 3, 5, or 10 seconds; duration choices are engineering tests;
- first 5 seconds, then at most one existing fix every 30 or 60 seconds; first
  available fix starts a slot, rejected/invalid fixes also consume slots;
- first 5 seconds, then 2-second bursts in every 60-second slot starting at t=5s.

Remove fixes BEFORE any Localizer observation or history update, not only at the
correction stage. Preserve original message stamps/receipts and speed/raw-s arrays.
No invented fixes, extrapolated road, initial on-map oracle, extra sensors or
parameter tuning. Report all scenarios, counts, outputs and missing positions.

Exact recorded-input reproduction is required. A scenario producing no positions
has zero coverage and null accuracy; it is NOT a pass for localization. Tests of
the audit harness may pass even when the audited estimator fails a scenario.
This is one previously inspected bag, not hidden-test statistics or 19-bag
validation. No main switch, no ROS or clock/executor/resource certification.
