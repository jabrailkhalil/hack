# Pre-measurement clarification; no H36 train/development payload opened yet

PLAN commit a7e3436adbb7cfc614d8ea367205103cac8c786c remains immutable.

Read exact existing low_speed_windows in tools/research_R3_H24/develop.py at 6b3a11a68b83ee7b680b3b283f4800726c7b84cd, blob 2141a444fd72a71277b8e8223c3ec235f6b999e9. The pinned PR13 predicate ALSO requires u>=0. This term was omitted in the descriptive PLAN paragraph; use the full original predicate, not a changed safety suite: valid & abs(f-r)<.15 & 1<(f+r)/2<2 & u>=0 & t>max(25,.1*t_end) & t<t_end-25. Durations 3 and 5 s unchanged. No admission threshold changed.

The conditional physical increments apply existing +/-max_accel clipping to drive-minus-resistance at b=0 before adding the profiled b*duration in the offline loss. Thus the nuisance model is an additive conditional approximation, not exact recursive simulation with an arbitrary load inside saturation. Constant-load invariance tests apply to the valid additive model, with interior b and inactive physical saturation. Runtime retains exact v8 clipping including its own legacy disturbance. Saturation/input timing/teacher-forcing limitations will be reported, not hidden as a different runtime.

Local source/env preflight: exact Python3.13.5/NumPy2.3.5/SciPy1.17.0, 156 original unit tests, 43 original integrity tests and 14 H36 synthetic tests passed. Mathematical Wolfram check confirmed quadratic projection, shift invariance, convex soft-L1 scalar profiling and removal of a constant regressor. No candidate accuracy claims. No data selection/gate was adjusted using H36 measurements.
