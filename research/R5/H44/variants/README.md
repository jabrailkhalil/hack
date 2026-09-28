# H44 research-only parameters — REJECTED, not for promotion

`gnss.yaml` is the only selectable candidate G; `wheel.yaml` is its matched-target attribution control W, not a fallback. Both preserve the complete pinned v8 profile except the original torque/power/brake values. Runtime code, class, readout and guards are unchanged. The old comments in the copied profile are retained verbatim, not a claim that this is the canonical profile.

Normal checkout/launch continues to use canonical v8. An explicit params_file can load a research YAML, but enabled installed ROS has NOT been benchmarked. No deployment recommendation. The numerical evaluation used the exact full configurations in ../fitted/*.json with GuardedReadoutObserver.

../fitted/FIT_LOCK.json is the original completed-fit manifest, NOT a validation authorization. Bulk metrics.json and predictions.npz named by that manifest are in the conversation evidence archive; compact Git files are enough for develop.py and cost.py replay, not the complete fitting audit. Validation/test were not opened. Do not change the fitted values or rerun optimization to rescue the measured negative result.
