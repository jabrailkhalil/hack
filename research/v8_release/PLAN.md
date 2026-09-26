# Release check for the already selected residual070

Baseline b2783206000091ab11a1c11ac3ff79082188a4fb; selected numerical/source freeze 0ac3e7caa0ced4bcafc18cecb5eb226e0f7bb2da; research/report head 55b5793d4f4faff4d617f7be9202d19acb39eb9b. No new candidate selection or fitting on validation. The exact changed bound remains 0.7000000000000001. Existing research pins, scorer, split and all previous evidence are unchanged.

## Validation stage

Only main and the frozen disturbance_070 candidate, on every one of the 19 validation bags in the immutable plan_v3/split_v3. Both GNSS receivers; missing reference stays null. Retain original frozen membership and explicitly disclose content duplicates, not independent trips. Same source clock, initialization, masks, anchors, original bias/dropout/lock faults. Controller is available in wheel dropout. Run clean, original cropped faults, full faulted recordings, and the already published low-speed/abrupt/slow generators. Independently reproduce the known v8 validation fingerprint before drawing a conclusion. Preserve per-bag/per-receiver metrics, arrays, source/data hashes and access journal. Final-test measurement payloads are not extracted or opened.

Publish overall and separate 30618/30639 results; the target is 30618 according to the user-provided organizer summary. Engineering admission requires clean/pooled/original-fault regression <=0.5%, clean/full-faulted scalar-distance regression <=1%, supplemental event regression <=0.5%, for all and target scopes. No new individual false stops/nonrecoveries, coverage loss, causal/reset errors. Per-bag clean worsening <=max(0.005 m/s,5%). Preserve missing cases and pre-existing unresolved recoveries. Meaningful gain is >=2% clean or >=5% original event error on the target; a development gain is not evidence of validation gain. Do not change these gates after results. No profile selection by bag name at runtime.

After a failed validation stop this candidate's promotion; do not tune it on validation. Further work has a separate development-only branch and must disclose adaptation. Reused validation is not an independent test or official XYZ score. Source-group-macro, pooled and scalar-span distance remain distinct. GNSS is evaluation-only.

## Deployment stage

Verify the exact selected YAML/JSON through the real installed guarded ROS node. Exercise input_stamp and ros_clock, actual GetParameters, velocity/position publication, faults and integral continuity. Check default-installed surface, package build and existing tests. Run in ROS Humble and the existing offline 2 CPU / 500000000-byte constraint; preserve failures/limitations. Do not describe skipped/unstarted CI as passing. Candidate and v8 numerical core are identical; changing the default profile still requires selected-profile verification.

Only after numerical and deployment admission update the canonical installed profile/launch and ACTIVE_SOLUTION consistently, keeping historical v8/v4 freezes unchanged, and merge with an expected head SHA. No force push or automatic merge on mere workflow completion. Test final default selection again. Main remains v8 until admission completes.

## Transport

prepare.py downloads the existing checksum-pinned organizer archive but extracts ONLY validation DBs and metadata, verifies each SHA, and supplies a transport receipt. No test SQL or decoded values. No external credentials, permissions or data visibility changes. A source ZIP and validation-only data ZIP may be retained as private Actions artifacts for 7 days to permit local verification if remote execution is unavailable. If runtime or input staging fails, record the blocker without claiming release success.
