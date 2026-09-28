# R5-H46 — untrained interface checkpoint

DEPENDENCY_PENDING / NOT_EVALUATED. No fitted global_and_vehicle_parameters.json exists. Synthetic fixtures in test_h46.py are unit fixtures, not training results. No new ROS executable/launch/default is installed.

## Runnable checks from this branch

```bash
PYTHONPATH=src/reserve_odometry:research/R5/H46 python -m unittest discover -s research/R5/H46 -p test_h46.py -v
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m pip install -r requirements-research.txt
python -m unittest discover -s research/tests -v
```

## Missing real components

The existing Library records for R5_H42_teacher_component.zip and R5_H43_atlas_handoff.zip were found, but actual materialization returned: `This Project file does not have an authorized raw-byte materialization path.` This is not a scientific rejection. GitHub publication receipts explicitly are not the full teacher/atlas arrays. Do not regenerate H42/H43 or turn expected pins into an actual dependency lock.

After the actual two ZIPs become available, preflight_tools/precheck_components.py performs only outer transport/manifest checks. Native producer payload verifiers and the fold compatibility bridge from the original wave-2 package remain mandatory, using actual producer folds. No training is authorized by dependency_probe.py, even when it exits 0.

## Delivery scope

Git contains the preregistration, runtime selection interface, optimization primitives, 25 interface tests, transport verifier and expected pins. The complete conversation checkpoint additionally includes the unchanged launch contracts/tools, exact 320-file source receipt, baseline-only development driver and its 5 tests, all per-bag baseline metrics, data hashes and local logs. Its baseline-only measured local commit is a54438a74c7f169daf6761a13a3210d36a55db72, based on a local verified snapshot rather than remote ancestry. This is NOT a fitted candidate SHA. Runtime selection/test source bytes are cross-checked against the published Git blobs.

For baseline-only reproduction, use the supplied full R5-H46 checkpoint/patch on the exact baseline (not an arbitrary updated main). The baseline_preflight.py script has only a development role and no fitting/validation entry point. The complete local package is not an Actions artifact and no CI run is claimed for H46 here. See reports/research_R5/H46/REPORT.md for observed results and boundaries.
