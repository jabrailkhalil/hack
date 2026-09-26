# V8 targeted development: bounded exploratory search

Baseline main b2783206000091ab11a1c11ac3ff79082188a4fb; numerical v8 unchanged from e3b0c9c. User requests improvements in jabrailkhalil/hack, not the colleague web repository. Main is not to be changed without comparison.

Motivation known before this run: the earlier traction-only H44 ablation regressed the target vehicle 30618 by 9.9353% in original fault-event RMSE. Do not transplant its parameters. User-supplied organizer summary identifies 30618 as the scored vehicle; this statement has not been independently verified here. Always report 30639 and combined results as well.

Budget round 1, fixed before new candidate measurements: baseline plus seven candidates: brake*0.90; brake*1.10; brake*1.20; torque and power*0.90; power*0.90; torque*0.90; preserve the already available output age correction during genuine wheel loss, without feeding it back into the inner observer. All unspecified Config/readout/Timeline/scorer/units/fault placement remain v8. No GNSS/IMU/bag-ID/fault oracle as runtime input. No per-bag parameters. Each model starts with its own configuration and state. Source bytes/parameters and execution logs saved before replay.

Round 1: all 17 frozen development bags, clean and original cropped faults; use unchanged scorer and source-time timeline, both GNSS receivers, missing=null. Preserve duplicate membership of the historical protocol and provide distinct-DB sensitivity. Baseline must reproduce published fingerprint. Compare 30618 / 30639 / all separately. Candidate search is EXPLORATORY on reused development, not an independent test or training-only identification. Do not relabel this as a held-out result.

Investigate candidates with >=5% target original-fault improvement, <=0.5% target clean/pooled regression, <=1% clean distance, no coverage loss/new false stops/new individual nonrecoveries, and <=0.5% combined fault regression. Then run full-faulted distance, low-speed, abrupt/slow common-mode and mechanism tests before a validation freeze. Combined and target full-faulted distance regression <=1%. Other-vehicle regression and all worst cases must be disclosed. Preserve all rejected variants. No threshold changes after outcomes. A further diagnostic round, if needed, must be separately recorded before its measurements; never conceal earlier trials.

Validation only after an eligible development candidate and separately committed source/config freeze; no final-test measurement IO in this task. Any final main promotion also requires enabled installed ROS verification. Publishing an experimental branch/PR is not promotion.

Available local data: verified source snapshot, 17 development DBs from GitHub Actions artifact 10902149285, prior full native evidence. No official pathgraph payload available; position/XYZ improvements will not be invented or inferred from velocity RMSE. New work targets the actual velocity observer.
