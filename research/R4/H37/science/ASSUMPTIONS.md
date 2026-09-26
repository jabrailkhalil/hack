# R4-H37: assumptions and source scope

The formula is specified by the user, not attributed to an invented publication. Positive force/power/mass and q in [0,1] are assumed. The piecewise difference and bound apply at the SAME state and command, before actuator lag, adaptation, clipping, wheel fusion, and guarded readout. They do not establish accuracy, asymptotic observer stability or the physical meaning of this controller's command. Changing target can change learned disturbance even though its update equation is unchanged. SI wheel scale 1/3.6 remains the pinned empirical convention, not independently certified.

Wolfram worksheet and actual output (including parsing ambiguity) are retained; independent numerical piecewise/bound checks are in test_foundation.py/test_h37.py. No new Consensus/Scite request was made after their known quota stop. No paid sources were accessed. No external paper is required to derive these elementary local formulas.

Prior evidence actually read: full accessible body of R3-H24 PR45 via authorized GitHub API. It describes fitted static q maps, rejected at fixed v8 on development; its saturation ordering was unchanged. Its results are context only, not H37 training labels or H37 measured metrics.
Source: https://github.com/jabrailkhalil/hack/pull/45
The read scope is the PR body, not an externally referenced full scientific paper. No unverified report-commit binding is asserted.
