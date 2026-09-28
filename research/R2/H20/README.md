# H20 research factory (R2-v7-fixed)

`factory.baseline()` resolves the actual guarded v7 YAML and pristine core/readout.
`factory.candidate(alpha)` executes a private core with the two hooks represented
by `algorithm.patch`, and the unchanged guarded readout. It does **not** patch the
installed/canonical node. Merely checking out this branch does not enable H20 in
ROS. The only predefined enabled strengths are `0.25` and `0.50`.

Reproduce from the measured source commit in an isolated environment:

```sh
python -m pip install -r requirements-research.txt
python -m unittest discover -s research/R2/H20/tests -v
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
python research/R2/H20/stage_data.py --stage development --journal /tmp/h20-staging.json
python research/R2/H20/run.py --stage development --output /tmp/h20-fresh --workers 2
```

The role-scoped staging command replaces the general unpack-all `get_dataset.py`
command from the PLAN command sketch. Same pinned organizer archive and decoder;
only the declared role's DBs are decompressed. This is an infrastructure/privacy
refinement, not a split, metric, parameter or acceptance change. No final/test DB
is opened or decompressed. A separate published freeze is required before any
validation stage. Reproducing the frozen run is not permission for further tuning.

`execute.sh` records actual commands and checks in an isolated Actions job. Original
full-suite/integrity failures are retained with exit codes; specific core, Timeline,
guarded and H20 tests must pass. Cost numbers are Python step/replay measurements,
not installed ROS latency/RSS certification. Research source transport may be
packed for connector transfer, but is expanded and committed to the dedicated
research branch **before** the first real measurement read.
