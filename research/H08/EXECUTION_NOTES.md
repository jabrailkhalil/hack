# H08 execution notes before measurement access

Run 36175133676 stopped in source preflight. The source patch was committed as 77ebf5d32953309f72ac1a53fff55f33d2faed27. The unchanged 70-test suite produced 66 passes and four failures: two assertions that core matches historical release bytes/hashes and two assertions that Config fields equal the historical profile schema. H08 adds one opt-in field and a new numerical path, so it is not the unchanged published release.

No train/validation/runtime measurements were opened by this H08 run. The numerical candidate, coefficients, gates, protocol and evaluator are unchanged. The next infrastructure invocation uses preflight.py to require exactly those four recorded failures and zero other failures/errors/skips, followed by separate H08 numerical and existing observer-behavior tests. Published tests and PROMOTION/FREEZE reports remain unchanged. Normal CI is still expected to fail those release-identity assertions; this is not a merge-ready patch.

The ROS shell no longer enables nounset before sourcing upstream ROS setup scripts. This changes only shell provisioning robustness, not the algorithm or measurement functions. No extra candidate or data-dependent tuning is introduced.
