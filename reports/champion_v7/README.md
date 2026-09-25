# Champion v7 integration

Canonical runtime candidate: **guarded v7 readout over the verified v5 inner
observer**, plus the independent low-speed common-zero wheel-lock protection.

Validation inherited from the fixed PR #14 experiment:
- clean group-macro speed RMSE: **0.114550 m/s** vs v5 **0.117138** (-2.21%);
- original fault-event RMSE: **0.538287 m/s** vs **0.538434** (no regression);
- scalar span distance RMSE: **4.59548 m** vs **4.63098** (-0.77%).

Separate low-speed lock extension from PR #13:
- event RMSE: **2.68877 -> 0.316586 m/s** (-88.23%);
- false-stop samples: **200 -> 0**;
- unrecovered comparisons: **1 -> 0**.

The 88.23% number applies only to the specifically injected low-speed lock
suite, not to ordinary driving or the full dataset. All selection used reused
validation/development data. The combined branch must pass installed ROS and
offline 2 CPU / 500 MB checks before promotion to main. Historical v4 evidence
and archive remain immutable.
