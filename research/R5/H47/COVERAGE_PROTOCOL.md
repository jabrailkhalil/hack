# H47 — continuation: natural faulty-example coverage only

This is a prospective operational specification of the next stage in the unchanged
PLAN (49fd44ffd5216526c757b2c9b8eb04a88b07ddce), not another hypothesis, classifier
variant, or candidate freeze. Resume source is 5715837a035bb43eff00de719b84f3b3e231ebdd.
No H47 measurement payload or label has been decoded before writing this file.

## Inputs and scope

Baseline b2783206000091ab11a1c11ac3ff79082188a4fb, tree
973d50d288e050325ee1c71a90fa8d81f2a099af. Existing features.py/offline_labels.py,
all 320 canonical files, source-time grid, Timeline arrival ordering and full
champion_v8 parameters stay byte-identical. This stage adds only a data adapter,
coverage counter, tests and immutable results. It has no fitting command.

The already executed native verifiers validate 85 teacher and 53 atlas files;
actual producer fold representations passed the supplied semantic bridge. A new
combined lock additionally binds the exact source files and all 64 train DBs before
SQLite. Development, validation and final/test payloads are not extracted or read.
H43 is a required verified dependency, never a label source or training table.

## Replay and label data separation

Every original train bag, including duplicates and missing-reference bags, is
replayed in original `ORDER BY m.timestamp,m.id` vehicle arrival order, with the
unchanged decoder/scales, native Timeline at 20 Hz and zero deliberate delay.
Only the three allowed vehicle topics are selected from SQLite. Both a direct
native v8 and the passive H47 probe run from fresh state; every returned Estimate,
held input and every native state field is compared on each tick. Timeline counters,
queues and schedule must also agree. No outputs are replaced by an offline oracle.

Only AFTER a bag's vehicle replay completes does the offline stage open its frozen
teacher NPZ. It reads exactly `stamp_ns`, `speed_mps`, `accepted`; no recalculation
of H42 quality or teacher. All timestamps are represented relative to that bag's
unchanged `sensor_start_ns` (subtract integers before conversion to seconds).
The indexed nearest lookup calls the existing `unique_nearest` function on a
sorted .05 s candidate slice; randomized and boundary tests compare it with the
unindexed reference. Duplicate/tied accepted times abstain.

Both current feature rows must be READY (as required by existing label interface).
The existing `proxy_pair_labels` is called without changing its .20/.50 m/s bounds,
1 m/s minimum magnitude, .05 s matching or common/intermediate abstention.
Feature histories, OOD domains and hard gate eligibility are unchanged.

## Counting rules fixed before labels

The lexicographically first bag in each canonical `wire_sha256` equivalence class
is the coverage representative, chosen using metadata only. All other bags are
retained in raw per-bag audit, but cannot increase prerequisite counts. Wire hashes
are recomputed from permitted vehicle payloads with the canonical fingerprint
rule. No group or bag is dropped due to unfavorable targets.

A labelled sample identity is (bag, wheel channel, source timestamp); duplicate
label assignment is an error. A faulty pair has exactly one faulty channel under
the existing label interface. Clean counterpart updates count as clean samples.

For episode segmentation, sort faulty output times within ONE bag, collapse exact
duplicates, and start a new episode only after >1 s without a faulty update. Do not
turn a long continuous episode into independent events. Do not concatenate unrelated
bag clock domains or channel switches to fabricate two episode onsets. A qualifying
group has >=10 distinct faulty updates, >=100 clean updates and at least one of its
representative bags has >=2 episode onsets. This operationalizes the PLAN's >=2
separated onsets in the same bag/time domain. Per-bag onset times are retained;
raw fault-bearing group counts are also reported separately from qualification.

GO requires >=3 qualifying fit groups AND >=2 qualifying check groups. Check is
used only for the predeclared coverage prerequisite, never to tune labels, features,
thresholds or a model. Failure is INCONCLUSIVE / FOUNDATION_FAILED and no fit.
Passing coverage alone is not an odometry result or runtime improvement.

## Deliverables

New diagnostic-source commit before the measurement run, full dependency lock,
64 per-bag raw JSON/NPZ, original groups including empty ones, deduplicated fold
summary, access journal and exact source/trace hashes. No new RMSE is asserted in
this coverage-only stage. No artificial augmentation, classifier scores or altered
acceptance gates. Existing reports/checkpoints are not overwritten.
