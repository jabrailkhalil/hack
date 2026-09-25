#!/usr/bin/env bash
# Research-only orchestration. Existing CI and frozen promotion guards are NOT changed.
set -Eeuo pipefail
: "${GITHUB_SHA:?}" "${GITHUB_RUN_ID:?}" "${GITHUB_RUN_ATTEMPT:?}"
H01_EVIDENCE="${H01_EVIDENCE:-/tmp/H01-evidence}"
branch="checkpoint/parallel-H01-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
destination="reports/research_parallel/H01/$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
mkdir -p "$H01_EVIDENCE/logs"
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
checkpoint() {
  if test "$(git branch --show-current)" != "$branch"; then git switch -c "$branch"; fi
  mkdir -p "$destination/logs"
  if test -d "$H01_EVIDENCE/results"; then rsync -a --ignore-existing "$H01_EVIDENCE/results/" "$destination/"; fi
  rsync -a --ignore-existing "$H01_EVIDENCE/logs/" "$destination/logs/"
  git add "$destination"
  git diff --cached --quiet || git commit -m "research(H01): preserve immutable run evidence $GITHUB_RUN_ID"
  git push origin "HEAD:refs/heads/$branch"
}
finish() {
  status=$?
  trap - EXIT
  printf '{"hypothesis":"H01","source_commit":"%s","run_id":"%s","run_attempt":"%s","exit_code":%s,"test_evaluated":false}\n' "$GITHUB_SHA" "$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT" "$status" > "$H01_EVIDENCE/logs/EXECUTION.json"
  checkpoint || status=1
  exit "$status"
}
trap finish EXIT
base=984fdf2fc4faf05325249215d6b8541c0e68209a
git show "$base:src/reserve_odometry/reserve_odometry/core.py" > "$H01_EVIDENCE/logs/baseline_core.py"
git diff "$base" "$GITHUB_SHA" > "$H01_EVIDENCE/H01.patch"
tar -czf "$H01_EVIDENCE/reproduction-source.tar.gz" src tools tests research/parallel/H01 research/plan_v3.json research/split_v3.json requirements-research.txt
printf '%s\n' 'Standard CI remains unchanged. Four historical promotion guards intentionally fail for changed core/config schema; see run 36175727749. No published hashes or acceptance metrics are edited. This job gates algorithm behavior, not promotion readiness.' > "$H01_EVIDENCE/logs/KNOWN_CI_LIMITATIONS.txt"
for pattern in test_core.py test_timeline.py test_final_runtime.py test_candidate_configs.py; do
  PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -p "$pattern" -v 2>&1 | tee "$H01_EVIDENCE/logs/$pattern.log"
done
PYTHONPATH=src/reserve_odometry H01_BASELINE_CORE="$H01_EVIDENCE/logs/baseline_core.py" python -m unittest discover -s research/parallel/H01/tests -v 2>&1 | tee "$H01_EVIDENCE/logs/H01-tests.log"
python -m compileall -q src research/parallel/H01
python -m pip install -r requirements-research.txt 2>&1 | tee "$H01_EVIDENCE/logs/dependencies.log"
python tools/get_dataset.py 2>&1 | tee "$H01_EVIDENCE/logs/dataset.log"
python research/parallel/H01/run.py --stage development --output "$H01_EVIDENCE/results" --workers 2 2>&1 | tee "$H01_EVIDENCE/logs/development.log"
# Failure to publish the selected candidate prevents validation access.
checkpoint
if test -f "$H01_EVIDENCE/results/FREEZE.json"; then
  python research/parallel/H01/run.py --stage validation --output "$H01_EVIDENCE/results" --workers 2 2>&1 | tee "$H01_EVIDENCE/logs/validation.log"
else
  echo 'No safe development candidate: validation remains unopened.' | tee "$H01_EVIDENCE/logs/validation.log"
fi
