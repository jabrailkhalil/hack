# Pre-data corrections

1. First local diagnostic test run: 16 pass / 1 failure. Python list equality treats independently produced diagnostic NaN as unequal. Prefix output/state checks passed. Replaced only the array assertion with numpy.testing.assert_array_equal (NaN in matching positions allowed). No data, gates, observer or mathematical target changed. Original log retained in local evidence.
2. Corrected pre-publication SUMMARY status to NOT_ATTEMPTED; checkpoint publication is a later independently verified action.

Before data IO, added explicit unexpected-reset/future-held-input assertions and separate published versus all-tick counts. Diagnostic masks, estimator output and admission unchanged.
