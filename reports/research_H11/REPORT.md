# Champion v8: common-mode jump quarantine

Base: champion v7 on main `65bba39ed05c781f3f69a65c02f69931152cbfd9`.
H11 was preregistered before implementation. The only new parameter is
`common_mode_quarantine_s=1.5`.

When both wheel channels produce a fresh `RATE_ANOMALY` within the existing
pair-skew window, only common-mode `REACQUIRING` is blocked for 1.5 s of source
time. Ordinary valid fusion, single-wheel fallback, zero-lock protection and
post-dropout recovery are unchanged.

Fixed validation + original fault suite (698891 matched speed samples):
- clean group-macro RMSE: **0.114549861 -> 0.114549861 m/s** (exact);
- pooled RMSE: **0.216406794 -> 0.216406794 m/s** (exact);
- scalar span distance RMSE: **4.595480653 -> 4.595480653 m** (exact);
- original fault-event RMSE: **0.538286783 -> 0.538286783 m/s** (exact);
- false stops and unrecovered counts unchanged.

Dedicated deterministic common-mode +5 m/s suite (0.7 s and 1.2 s, anchors
chosen from vehicle data before reference scoring):
- group-macro event RMSE: **0.092437932 -> 0.063561937 m/s (-31.24%)**;
- REACQUIRING ticks: **47 -> 0**;
- false stops: **0 -> 0**;
- unrecovered: **0 -> 0**;
- mean confirmed recovery: **0.3790 -> 0.3182 s**.

Run: https://github.com/jabrailkhalil/hack/actions/runs/36177281317
Raw evidence: branch `checkpoint/H11-36177281317-1`.

This is reused validation plus injected faults, not an independent final test and
not an official score. No GNSS/IMU is used at runtime.
