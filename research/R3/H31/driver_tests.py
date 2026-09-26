"""Synthetic driver tests, no dataset or held-out measurement IO."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import run as r

class DriverTests(unittest.TestCase):
    def test_role_access_denied_before_file(self):
        data=r.Data()
        for bag in data.plan['splits']['test'][:1]:
            with self.assertRaises(PermissionError):data.get(bag,'development')
            with self.assertRaises(PermissionError):data.get(bag,'test')
    def test_original_scorer_and_exact_inner_off(self):
        events=r.np.array([(i*.05,ch, .2 if ch==0 else 5.) for i in range(801) for ch in (0,1,2)],float)
        refs={'master':[(i*.05,5.) for i in range(801)],'rover':[]}
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);meta=dict(case_id='synthetic',suite='clean',bag='synthetic',group='synthetic',role='synthetic')
            b=r.score_case(events,refs,meta,p,True)
            c=r.score_case(events,refs,meta,p,False)
            self.assertEqual(b['receivers']['master']['v8'],c['receivers']['master']['v8'])
            self.assertEqual(c['audit']['v8']['canonical_output_sha256'],c['audit']['H31']['canonical_output_sha256'])
            self.assertEqual(c['audit']['H31']['stats']['limit_failures'],0)
    def test_guard_cannot_be_relaxed_by_other_metrics(self):
        events=r.np.array([(i*.05,ch,.2 if ch==0 else 5.) for i in range(801) for ch in (0,1,2)],float)
        refs={'master':[(i*.05,5.) for i in range(801)],'rover':[]}
        with tempfile.TemporaryDirectory() as td:
            rows=[]
            for suite in ('clean','original','low_speed','common','transition'):
                meta=dict(case_id='s-'+suite,suite=suite,bag='s',group='g',role='synthetic')
                if suite!='clean':meta['fault']=dict(kind='dropout',start=25.,end=30.)
                rows.append(r.score_case(events,refs,meta,Path(td)))
            s={n:r.summary(rows,n) for n in ('v8','H31','equal_weight')}
            modified=deepcopy(s);modified['H31']['fault_rmse']=s['v8']['fault_rmse']*1.01+1e-6
            result=r.evaluate_gate(rows,modified,dict(passed=True))
            self.assertIn('aggregate_regression:fault_rmse',result['reasons'])
            self.assertFalse(result['validation_authorized'])
            self.assertFalse(result['coverage']['passed'])

if __name__=='__main__':unittest.main()
