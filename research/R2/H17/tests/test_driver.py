"""Driver/role checks use synthetic records only; not accuracy evidence."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('h17_driver_test',HERE/'driver.py')
d=importlib.util.module_from_spec(spec);sys.modules[spec.name]=d;spec.loader.exec_module(d)


def rows():
    metric=dict(n=20,coverage=1.,rmse=.1,mae=.08,bias=.001,p95=.2,false_stop_samples=0,
                distance_surrogate={'reanchored_span_rmse_m':1.})
    rt=dict(causal_errors=0,resets=0,dropped=0,catchups=0,mode_counts={})
    clean=dict(bag='b',group='g',receivers={'master':{'R2_v7':deepcopy(metric),'H17_L050':deepcopy(metric)}},
               runtime={'R2_v7':deepcopy(rt),'H17_L050':deepcopy(rt)})
    stress=deepcopy(clean);stress['fault']=dict(kind='dropout',start=10.,end=15.)
    for m in stress['receivers']['master'].values():m.update(event_rmse=.2,recovery_s=.5)
    return [clean],[stress],[]


class DriverTests(unittest.TestCase):
    def test_effective_profile(self):
        p=d.profile();self.assertEqual(p['readout']['gain'],1)
        self.assertEqual(p['config']['wheel_time_compensation'],0)
    def test_perfect_tie_fails_gain_not_regressions(self):
        c,s,e=rows();self.assertTrue(d.admission(c,s,e,'H17_L050',False)['passed'])
        self.assertEqual(d.admission(c,s,e,'H17_L050',True)['rejection_reasons'],['insufficient_gain'])
    def test_clean_gain_passes_exact_threshold(self):
        c,s,e=rows();c[0]['receivers']['master']['H17_L050']['rmse']=.0979
        self.assertTrue(d.admission(c,s,e,'H17_L050',True)['passed'])
    def test_fault_and_distance_guards(self):
        c,s,e=rows();s[0]['receivers']['master']['H17_L050']['event_rmse']=.202
        c[0]['receivers']['master']['H17_L050']['distance_surrogate']['reanchored_span_rmse_m']=1.02
        r=d.admission(c,s,e,'H17_L050',False)['rejection_reasons']
        self.assertIn('aggregate_regression:fault_rmse',r);self.assertIn('aggregate_regression:distance_rmse',r)
    def test_pooled_guard(self):
        c,s,e=rows();c[0]['receivers']['master']['H17_L050']['rmse']=.101
        self.assertIn('aggregate_regression:pooled_rmse',d.admission(c,s,e,'H17_L050',False)['rejection_reasons'])
    def test_extra_new_unrecovered_blocks_selection(self):
        c,s,e=rows();extra=deepcopy(s);extra[0]['receivers']['master']['H17_L050']['recovery_s']=None
        self.assertTrue(any(x.startswith('new_unrecovered:extra') for x in d.admission(c,s,extra,'H17_L050',False)['rejection_reasons']))
    def test_existing_unrecovered_not_new(self):
        c,s,e=rows()
        for m in s[0]['receivers']['master'].values():m['recovery_s']=None
        self.assertTrue(d.admission(c,s,e,'H17_L050',False)['passed'])
    def test_coverage_and_false_stop(self):
        c,s,e=rows();m=c[0]['receivers']['master']['H17_L050'];m.update(n=19,coverage=.95,false_stop_samples=1)
        r=d.admission(c,s,e,'H17_L050',False)['rejection_reasons']
        self.assertTrue(any(x.startswith('coverage') for x in r));self.assertTrue(any(x.startswith('false_stop') for x in r))
    def test_modes_may_change_but_resets_may_not(self):
        c,s,e=rows();c[0]['runtime']['H17_L050']['mode_counts']={'SINGLE_WHEEL':5}
        self.assertTrue(d.admission(c,s,e,'H17_L050',False)['passed'])
        c[0]['runtime']['H17_L050']['resets']=1
        self.assertFalse(d.admission(c,s,e,'H17_L050',False)['passed'])
    def test_zero_and_missing_aggregates(self):
        self.assertFalse(d.regression(0.,0.,.005));self.assertTrue(d.regression(1e-9,0.,.005))
        self.assertTrue(d.regression(None,1.,.005));self.assertTrue(d.regression(0.,None,.005))
    def test_role_denied_before_checksum_or_sql(self):
        with tempfile.TemporaryDirectory() as temp:
            store=d.RoleStore(Path(temp),Path(temp)/'access.json')
            testbag=store.plan['splits']['test'][0];train=store.plan['splits']['train'][0]
            with patch.object(d.ev,'sha',side_effect=AssertionError('checksum must not run')),patch.object(d.sqlite3,'connect',side_effect=AssertionError('SQL must not run')):
                for bag,role in ((testbag,'test'),(testbag,'development'),(train,'development')):
                    with self.assertRaises(PermissionError):store.load_role(bag,role)
    def test_paired_really_uses_guarded_output(self):
        events=d.np.array([(i*.05,ch,val) for i in range(400) for ch,val in ((0,.4),(1,4+i*.01),(2,4+i*.01))])
        refs={'master':[(i*.05,4+i*.01) for i in range(400)],'rover':[]}
        sw,_=d.transitions(events);r=d.paired(events,refs,d.DELAYS,sw)
        self.assertTrue(r['canonical_off_exact'])
        self.assertTrue(any(x['published_v']!=x['inner_v'] for x in r['diagnostics']['R2_v7']['traces']) if r['diagnostics']['R2_v7']['traces'] else True)
        self.assertEqual(r['runtime']['R2_v7'],r['runtime']['R2_off'])


if __name__=='__main__':unittest.main()
