# Pre-data corrections

1. First local diagnostic test run: 16 pass / 1 failure. Python list equality treats independently produced diagnostic NaN as unequal. Prefix output/state checks passed. Replaced only the array assertion with numpy.testing.assert_array_equal (NaN in matching positions allowed). No data, gates, observer or mathematical target changed. Original log retained in local evidence.
2. Corrected pre-publication SUMMARY status to NOT_ATTEMPTED; checkpoint publication is a later independently verified action.

Before data IO, added explicit unexpected-reset/future-held-input assertions and separate published versus all-tick counts. Diagnostic masks, estimator output and admission unchanged.

After Actions failed with runner_id=0 and no steps/logs, added an explicit H33_SOURCE_RECEIPT path for git-free execution from the verified ZIP. It recomputes all 301 current hashes/modes and the Git tree; does not fake commit ancestry or change foundation/scoring. Added two receipt tests. No measurement data was opened and no rerun was triggered. Failed Actions source d4837cc66e09321e3104cc3e8f7387f8628fb7fd remains separately recorded.
