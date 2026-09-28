#!/usr/bin/env bash
set -Eeuo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export H20_SOURCE_SHA="${H20_SOURCE_SHA:-$(git rev-parse HEAD)}"
RID="${GITHUB_RUN_ID:?}-${GITHUB_RUN_ATTEMPT:?}"
OUT="reports/research_R2/H20/$RID"
CHECKPOINT="checkpoint/R2-H20-$RID"
mkdir -p "$OUT/logs"
printf '%s\n' "$H20_SOURCE_SHA" > "$OUT/measured-source-sha.txt"
cp reports/research_R2/H20/preregistered-01/PLAN.md "$OUT/PLAN.md"
cp research/R2/H20/algorithm.patch "$OUT/algorithm.patch"
git archive --format=tar.gz "$H20_SOURCE_SHA" research/R2/H20 src tools tests requirements-research.txt research/plan_v3.json research/split_v3.json > "$OUT/reproduction-source.tar.gz"
exec > >(tee -a "$OUT/logs/execute.log") 2>&1
set -x
python -m pip install -r requirements-research.txt
python -m compileall -q research/R2/H20 src/reserve_odometry/reserve_odometry
# Historical guards remain untouched; record full suite failures, do not hide them.
set +e
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v > "$OUT/logs/full-unit.log" 2>&1
FULL_RC=$?
python -m unittest discover -s research/tests -v > "$OUT/logs/research-integrity.log" 2>&1
INTEGRITY_RC=$?
set -e
printf '{"full_unit_exit_code":%s,"research_integrity_exit_code":%s}\n' "$FULL_RC" "$INTEGRITY_RC" > "$OUT/historical-test-status.json"
python -m unittest discover -s research/R2/H20/tests -v > "$OUT/logs/H20-unit.log" 2>&1
for MODULE in test_core.py test_timeline.py test_guarded_readout.py; do
  PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -p "$MODULE" -v > "$OUT/logs/$MODULE.log" 2>&1
done
python research/R2/H20/stage_data.py --stage development --journal "$OUT/development-staging.json"
python research/R2/H20/run.py --stage development --output "$OUT/experiment" --workers 2 > "$OUT/logs/development.log" 2>&1
# New checkpoint branch only. Never main/research branches or force-push.
git config user.name 'H20 research checkpoint'
git config user.email 'h20-research@users.noreply.github.com'
git switch -c "$CHECKPOINT" "$H20_SOURCE_SHA"
if [[ -f "$OUT/experiment/FREEZE.json" ]]; then
  git add -f -- "$OUT" ":!$OUT/logs/execute.log"
  git commit -m "research(H20): freeze selected development candidate before validation [$RID]"
  git push origin "HEAD:refs/heads/$CHECKPOINT"
  FREEZE_SHA=$(git rev-parse HEAD)
  printf '{"commit_sha":"%s","branch":"%s","published_before_validation":true}\n' "$FREEZE_SHA" "$CHECKPOINT" > "$OUT/experiment/FREEZE_PUBLICATION.json"
  python research/R2/H20/stage_data.py --stage validation --journal "$OUT/validation-staging.json"
  python research/R2/H20/run.py --stage validation --output "$OUT/experiment" --workers 2 > "$OUT/logs/validation.log" 2>&1
fi
# No candidate parameter changes after this point. New evidence only.
python - "$OUT" <<'PY'
import json,sys
from pathlib import Path
out=Path(sys.argv[1]);exp=out/'experiment'
last=exp/'validation/OUTCOME.json' if (exp/'validation/OUTCOME.json').exists() else exp/'development/OUTCOME.json'
status=json.loads(last.read_text());status['installed_enabled_candidate_ros']='not_performed'
status['full_unit_and_integrity']=json.loads((out/'historical-test-status.json').read_text())
(out/'STATUS.json').write_text(json.dumps(status,indent=2,ensure_ascii=False)+'\n')
PY
git add -f "$OUT"
git commit -m "research(H20): preserve measured results and limitations [$RID]"
git push origin "HEAD:refs/heads/$CHECKPOINT"
git rev-parse HEAD
cat "$OUT/STATUS.json"
