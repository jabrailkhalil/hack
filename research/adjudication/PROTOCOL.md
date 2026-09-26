# Strict single-main adjudication — 2026-09-26

## Authority and scope

User requests one primary solution in main after critical comparison, not indiscriminate merges. Preserve all branch history and old frozen evidence. Do not delete colleagues' branches or change repository visibility. Current main is pinned to e3b0c9c039d2953fbfcda51231263d38ef9f1024 (v8).

## Candidates and census

Inspect all currently accessible research PR verdicts; rejected, incomplete and unevaluated variants are not automatically promoted. Direct paired numerical comparison must include active v8 and the five implemented velocity candidates published by godknows1337: A, B, C, H1_10 and H2_050. D is a known-route geometry projection, not an alternative velocity estimator. Pin branch SHAs, code/model hashes and authors. Check that the six peer branches share the same implementation before reusing one source snapshot. Include simple front/rear/mean as diagnostic anchors where practical.

Peer refs initially supplied in the preceding census:
A 98accff0d97b2ff69a2307e30841d2dec788c1d3
B 46a81edf2a02ea170af5bde818746aea808e728a
C 84342ac394f0de4e3f79e42e1b3a6526ebb6608a
D 13c86f38e18d23ae964b23b0ee2ef63cca4a799a
H1_10 b33d8b42262a5aabe0fdc22ac7b65b54d507798e
H2_050 f76e4d729801a479b036a18a1bbe69cf47877e84

## Immutable evaluation basis

Use the existing 19 validation bags, both GNSS receivers, nearest matching <=50 ms, original group aggregation, the established original fault windows, and already defined abrupt/slow common-mode windows. No parameter fitting, no selecting clean examples, no changing data/reference masks by estimator error. Do not open final-test measurements for selection. Reused validation is not an independent generalization test. Missing reference remains N/A. Common-mode scenarios are reported separately, not silently included in the original aggregate.

Use identical causal input order, timestamps, units and output grid. Run the actual imported code; a wrapper may translate interfaces but must not fix/retune its equations. Document any scheduling sensitivity, pre-initialization coverage and stale outputs. Validate that raw wheel scale is applied exactly once. Confirm the active v8 reproduces its published 0.1145498613174081 group-macro clean RMSE. Preserve per-bag/per-receiver and per-fault tables, not only aggregates.

## Selection gates (fixed before new numerical results)

Replacement requires: finite causal outputs; no reduced valid-output coverage; no added false stops or unrecovered original failures; clean and original-fault aggregate RMSE regression <=0.5%; pooled clean regression <=0.5%; scalar span-distance regression <=1%; each clean bag/receiver regression <=max(0.005 m/s,5%). It must improve clean RMSE >=2% OR original-fault RMSE >=5%; better special-case diagnostics alone do not justify worse primary metrics. Report worst-case/common-mode weaknesses even if a candidate passes. For multiple eligible candidates prefer Pareto dominance; without clear dominance retain the proven deployed incumbent and explain the trade-off rather than inventing post-hoc score weights. This selects the best eligible deployment under explicit criteria, not a claim of a universal optimum.

A newly selected runtime must build and run in ROS Humble with no network under 2 CPU / 500000000 bytes, pass the installed launch/clock/fault tests, and have one canonical public launch and configuration. Unverified candidate ROS performance must not borrow incumbent measurements.

## Main consolidation

After evidence is frozen, main should present exactly one primary runtime/launch/configuration. Keep historical results and configurations outside the installed default surface; retain branch history. Clean documentation so old archives cannot be mistaken for the active release. Do not overwrite historical final-test/ZIP checksums. Re-run tests after packaging changes and merge only an exact reviewed commit after checking concurrent main changes. Intermediate evidence is committed to this review/checkpoint branch, not main.
