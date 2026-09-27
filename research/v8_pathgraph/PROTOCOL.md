# Fixed Pathgraph experiment (before position-score computation)

Baseline: c8858384 PR62, canonical v8 and frozen residual070 unchanged. Inputs:
two supplied points/paths JSONs and the previously inspected checker bag. No
reference pose, velocity, heading, fitted transform, route s or bag ID enters
Localizer. Additional-bag exploratory experiment, NOT independent validation.

Map inspection already disclosed: only points and paths, about4.71km, no CRS or
origin metadata, no connecting loops. Geometric reference inspection found
uncovered start/end. It supplies no estimator anchor.

EXPERIMENTAL transform hypothesis: WGS84 UTM37N minus (300000,6100000)m. Inferred
from GNSS projection and numerical map range, NOT confirmed by files/organizers,
NOT fitted to the reference trajectory. GNSS altitude does not force map heights.
Unconfirmed use needs explicit allow_hypothesis=true.

Fixed: rover arm (2.563,0,3) from prior organizer summary supplied by user; 3D arc;
exact original point_indices, stored tang for yaw; XY projection onto antenna
locus with segment yaw/grade. Course only from prior same-receiver fixes within
2s, >=.3s and >=2m displacement. No GNSS velocity. Valid status0/1/2, age<=2s,
raw-history gap<=.15s. Heading within60deg, cross-track<=8m, ambiguity margin.5m
and separation8m. No invented edges, route switching, clamping or extrapolation.

Three fixed modes: initial_window first5s from first model output, no corrections;
first_on_map accepts first valid on-map fix at any time, no later corrections;
sparse uses same initialization and >=30s slots, gain.25, correction<=1m,
innovation<=40m. Rejected corrections consume slots. Engineering settings, not
guaranteed GNSS availability or tuned parameters.

Unchanged native source-clock replay at20Hz, each of two model profiles. Publish
all modes, coverage and missing intervals. No position before initialization or
outside map. Subset RMSE NEVER becomes full-bag RMSE. Report each subset and SAME
intersection for fair comparisons. Uploaded checksum-pinned checker arithmetic
offline, not live ROS/DDS. Ground-truth-to-map projection is a separately labelled
geometric oracle diagnostic, not an estimator. Speed/raw s must remain unchanged.

No parameter selection after results; preserve failures/hashes. Main unchanged
pending CRS confirmation, route coverage, installed ROS and numerical admission.
