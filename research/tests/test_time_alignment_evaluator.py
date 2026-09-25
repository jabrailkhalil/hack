"""Ensure the v6 confirmation cannot silently select data or weaker baselines."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('paired_v6', ROOT / 'tools/research_time_alignment/compare.py')
v6 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v6
spec.loader.exec_module(v6)


class TimeAlignmentEvaluatorTests(unittest.TestCase):
    def test_baseline_and_selected_configuration(self):
        models = v6.models()
        self.assertEqual(models['main'][1].adaptation_tau_s, 8.)
        self.assertEqual(models['main_v5'][1].adaptation_tau_s, .5)
        self.assertEqual(models['candidate'][1].wheel_time_compensation, 1.)
        self.assertEqual(models['candidate'][1].adaptation_tau_s, .5)

    def test_test_role_is_denied_before_database_io(self):
        store = v6.ev.ex.Store()
        bag = store.plan['splits']['test'][0]
        with patch.object(v6.ev.ex.Store, 'load', side_effect=AssertionError('DB IO attempted')):
            with self.assertRaises(PermissionError):
                v6.worker((bag, ROOT / 'nonexistent', Path('/unused'), False))

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            marker = p / 'marker.txt'
            marker.write_text('preserve evidence')
            with self.assertRaises(FileExistsError):
                v6.run(p, ROOT / 'nonexistent', 1, False)
            self.assertEqual(marker.read_text(), 'preserve evidence')

    def test_missing_reference_cannot_pass_acceptance(self):
        metric = dict(macro_rmse=None, fault_macro=None, distance_macro=None,
                      false_stops=0, fault_false_stops=0, fault_missing_recovery=0)
        summary = {name: copy.copy(metric) for name in v6.NAMES}
        self.assertFalse(v6.decision([], summary)['eligible'])

    def test_fault_regression_gate_is_enforced_against_v5(self):
        metric = dict(macro_rmse=1., fault_macro=1., distance_macro=1.,
                      false_stops=0, fault_false_stops=0, fault_missing_recovery=0)
        summary = {name: copy.copy(metric) for name in v6.NAMES}
        summary['candidate'].update(macro_rmse=.9, fault_macro=1.051)
        outcome = v6.decision([], summary)
        self.assertFalse(outcome['eligible'])
        self.assertIn('main_v5: fault_macro', outcome['rejection_reasons'])
