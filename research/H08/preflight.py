"""Record the unchanged suite, and distinguish four frozen-release identities.

This does NOT make the normal CI green or waive promotion gates. Any unexpected
failure/error/skip blocks research; the four release-identity failures remain
failures in the log and JSON. No published tests, hashes or metrics are changed.
"""
import argparse
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src/reserve_odometry'))
EXPECTED = {
    'test_active_profile.ActiveProfileTests.test_active_source_hashes_are_pinned_separately',
    'test_active_profile.ActiveProfileTests.test_current_default_is_the_selected_profile',
    'test_active_profile.ActiveProfileTests.test_rejected_experimental_runtime_is_not_deployed',
    'test_adaptive_profile.AdaptiveProfileTests.test_only_adaptation_changes_from_main',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    failures = {test.id() for test, _ in result.failures}
    data = dict(tests_run=result.testsRun, successes=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
                full_suite_passed=result.wasSuccessful(),
                failures=[dict(test=t.id(), traceback=tb) for t,tb in result.failures],
                errors=[dict(test=t.id(), traceback=tb) for t,tb in result.errors],
                expected_release_identity_failures=sorted(EXPECTED),
                research_preflight_passed=(result.testsRun==70 and failures==EXPECTED and not result.errors and not result.skipped),
                promotion_ready=False,
                note='Frozen release identity failures are preserved; normal CI is NOT green.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists(): raise FileExistsError('Preserve prior preflight evidence')
    args.output.write_text(json.dumps(data, indent=2)+'\n')
    if not data['research_preflight_passed']:
        raise SystemExit('Unexpected test results: research remains blocked')
    print('H08_RESEARCH_PREFLIGHT: 66 passed, 4 recorded release-identity failures; NOT a full-suite PASS')


if __name__=='__main__':
    main()
