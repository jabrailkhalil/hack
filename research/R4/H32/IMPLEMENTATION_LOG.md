# Implementation log before candidate measurements

One H32_event_time candidate only. Implemented after foundation PASS and PLAN commit abacda82c1856e921a940894a1c8265b249c06e9. No fitting. Canonical src/tools unchanged.

The initial local queue implementation briefly appended the 32nd pending entry before dropping the farthest future event. Before any candidate data measurement it was changed to evict/reject before append, keeping <=31 pending + 1 predecessor even during an update. This is a bounded-memory coding fix, not a second scientific candidate. All 32 special tests then passed.

Local synthetic driver smoke: 3000 events, 620 output ticks, full feature-off equality and 14 nested canonical-driver metric fields exactly matched. These are synthetic checks, not real accuracy. Constant-command tests cover 6000 ticks; feature-off 6000 ticks, plus Timeline/overflow/late/stale/zero-lock/quarantine/20000 dense ticks and derivative/integral checks. Real-payload work starts only in the published development workflow.

Benchmark replay medians time the whole 70-second source span, following an unrecorded warmup replay. Per-step medians exclude the first 10 source seconds. Identical collectors are used for both. This distinction is retained in COST.json; neither value is a ROS latency measurement.
