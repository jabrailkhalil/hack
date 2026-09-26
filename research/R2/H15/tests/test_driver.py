import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('h15_driver',HERE/'run.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)

class DriverTests(unittest.TestCase):
    def test_actual_canonical_and_disabled_driver(self):
        events=[];refs=[]
        for i in range(400):
            t=i*.1;z=5+.2*d.np.sin(t)
            events.extend([(t,0,.2),(t,1,z),(t,2,z)])
            refs.append((t,z))
        row=d.paired(d.np.array(events),{'master':refs,'rover':[]},list(d.RIDGES))
        self.assertTrue(row['disabled_equivalence'])
        self.assertEqual(row['runtime']['off'],row['runtime']['baseline_v2'])
        for name in d.RIDGES:self.assertGreater(row['diagnostics'][name]['stats']['trusted_points'],0)

    def test_loader_forbids_test_before_io(self):
        with tempfile.TemporaryDirectory() as td:
            store=d.RoleStore(Path(td)/'access.json')
            for role in ('test','final'):
                with patch('sqlite3.connect',side_effect=AssertionError('IO reached')):
                    with self.assertRaises(PermissionError):store.load(store.plan['splits']['test'][0],role)

    def test_loader_forbids_relabeling(self):
        with tempfile.TemporaryDirectory() as td:
            store=d.RoleStore(Path(td)/'access.json')
            with patch('sqlite3.connect',side_effect=AssertionError('IO reached')):
                with self.assertRaises(PermissionError):store.load(store.plan['splits']['validation'][0],'development')

    def test_fixed_source_manifest_evaluator_hashes(self):
        m=json.loads((HERE/'baseline_manifest.json').read_text())
        for p in ('tools/finalization/evaluate.py','tools/research_v3/experiment.py','tools/research_v6/compare.py',
                  'tools/research_guarded/compare.py','research/split_v3.json'):
            self.assertEqual(d.sha(d.ROOT/p),m['sha256'][p])

    def test_zero_baseline_absolute_guard(self):
        self.assertEqual(d.change(0,0),0)
        self.assertIsNone(d.change(1e-6,0))

    def test_phase_anchor_vehicle_only(self):
        events=[]
        for i in range(1000):
            t=i*.1;u=.2 if t<35 else (0 if t<45 else -.2)
            events.extend([(t,0,u),(t,1,5),(t,2,5)])
        cases=list(d.phase_windows(d.np.array(events)))
        self.assertEqual(len(cases),2)
        self.assertAlmostEqual(cases[0][1]['start'],34.7)
        self.assertAlmostEqual(cases[1][1]['start'],44.7)

if __name__=='__main__':unittest.main()
