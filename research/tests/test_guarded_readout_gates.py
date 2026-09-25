"""Do not relax the 0.5% fault-regression gate to obtain a winner."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('guarded_compare',ROOT/'tools/research_guarded/compare.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class GuardedGateTests(unittest.TestCase):
    def evidence(self):
        summary={n:dict(macro_rmse=r,fault_macro=f,distance_macro=4.,false_stops=0,
                    fault_false_stops=0,fault_missing_recovery=0)
                 for n,r,f in [('main',.1,.5),('candidate',.097,.499)]}
        row=dict(bag='b',runtime={'main':{'causal_errors':0},'candidate':{'causal_errors':0}},
                 receivers={'master':{'main':dict(n=100,coverage=1.,rmse=.1),
                                      'candidate':dict(n=100,coverage=1.,rmse=.097)}})
        return [row],[],summary

    def test_strict_gate_accepts_real_gain(self):
        self.assertTrue(module.decision(*self.evidence())['eligible'])

    def test_pr11_size_fault_regression_is_rejected(self):
        clean,stress,summary=self.evidence()
        summary['candidate']['fault_macro']=summary['main']['fault_macro']*1.0195846298362425
        self.assertIn('aggregate regression: fault_macro',module.decision(clean,stress,summary)['rejection_reasons'])

    def test_exact_fault_gate_boundary(self):
        for multiplier,accepted in [(1.005,True),(1.005001,False)]:
            clean,stress,summary=self.evidence();summary['candidate']['fault_macro']=.5*multiplier
            self.assertEqual(module.decision(clean,stress,summary)['eligible'],accepted)

    def test_missing_reference_and_coverage_cannot_manufacture_gain(self):
        clean,stress,summary=self.evidence();summary['candidate']['fault_macro']=None
        self.assertFalse(module.decision(clean,stress,summary)['eligible'])
        clean,stress,summary=self.evidence();clean[0]['receivers']['master']['candidate']['n']=99
        self.assertFalse(module.decision(clean,stress,summary)['eligible'])

    def test_changed_runtime_and_per_bag_regression_rejected(self):
        for field in ('runtime','rmse'):
            clean,stress,summary=self.evidence()
            if field=='runtime':clean[0]['runtime']['candidate']['causal_errors']=1
            else:clean[0]['receivers']['master']['candidate']['rmse']=.106
            self.assertFalse(module.decision(clean,stress,summary)['eligible'])

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):
                module.run(Path(tmp),ROOT/'dataset/data',1)

    def test_test_role_refused_before_sqlite_io(self):
        bag=module.ev.ex.Store().plan['splits']['test'][0]
        with patch('sqlite3.connect',side_effect=AssertionError('Must not open any DB')):
            with self.assertRaises(PermissionError):
                module.worker((bag,Path('/nonexistent'),Path('/nonexistent'),False,True))

    def test_readout_cannot_refit_physical_parameters(self):
        models=module.models()
        self.assertEqual(models['main'][1],models['candidate'][1])
        self.assertEqual(models['main'][1].adaptation_tau_s,.5)
        self.assertEqual(module.NAMES,('main','candidate'))
