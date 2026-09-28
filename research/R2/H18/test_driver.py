import copy
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest

SPEC=importlib.util.spec_from_file_location('h18_driver',Path(__file__).with_name('run.py'))
r=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(r)


class DriverTests(unittest.TestCase):
    def test_role_isolation_before_io(self):
        for role in ('train','development','validation'):
            store=r.RoleStore(role)
            for other in ('train','development','validation','test'):
                if other==role:continue
                bag=store.plan['splits'][other][0]
                with patch('sqlite3.connect',side_effect=AssertionError('must not open')):
                    with self.assertRaises(PermissionError):store.load(bag)
        with self.assertRaises(PermissionError):r.RoleStore('test')

    def events(self):
        return r.np.array([(i*.1,ch,(.1 if ch==0 else 5.+.02*i)) for i in range(650) for ch in range(3)],float)

    def test_factory_output_reference_and_original_suite(self):
        events=self.events()
        refs={x:[(i*.05,5+.01*i) for i in range(1300)] for x in ('master','rover')}
        score,_,check=r.paired(events,refs,.01,check=True)
        self.assertTrue(check['direct_canonical_exact']);self.assertTrue(check['feature_off_exact'])
        cases=list(r.guarded.fault_windows(events));self.assertEqual(len(cases),4)
        for fault,window in cases:
            s,d,_=r.paired(window,refs,.01,fault,detail=True,check=True)
            self.assertEqual(s['runtime']['candidate']['causal_errors'],0)
            self.assertEqual(s['receivers']['master']['baseline']['n'],s['receivers']['master']['candidate']['n'])
        badrefs={'master':[(0.,-1000.)],'rover':[]}
        s,_,c=r.paired(events,badrefs,.01,check=True)
        self.assertEqual(check['outputs_sha256'],c['outputs_sha256'])

    def test_gate_absolute_zero_and_new_individual_unrecovered(self):
        events=self.events();refs={x:[(i*.05,5.+.01*i) for i in range(1300)] for x in ('master','rover')}
        score,_,_=r.paired(events,refs,0.)
        clean=[dict(bag='b',group='g',**score)]
        fault,window=next(r.guarded.fault_windows(events));s,_,_=r.paired(window,refs,0.,fault)
        stress=[dict(bag='b',group='g',fault=fault,**s)]
        self.assertTrue(r.gates(clean,stress,False)['passed'])
        for receiver in s['receivers']:
            s['receivers'][receiver]['baseline']['recovery_s']=0.
            s['receivers'][receiver]['candidate']['recovery_s']=None
        out=r.gates(clean,[dict(bag='b',group='g',fault=fault,**s)],False)
        self.assertTrue(any(x.startswith('new_unrecovered') for x in out['rejections']))
        self.assertIsNone(r.pct(1.,0.))

    def test_no_future_calibration_features(self):
        o=r.CalibrationProbe(r.Config(**r.CFG),readout=r.READOUT)
        for i in range(100):
            t=i*.1;o.step(t,r.Sample(t,.1),r.Sample(t,5.),r.Sample(t,5.))
        self.assertGreater(o.residual_count,0)
        self.assertGreater(len(o.blocks),0)
        self.assertTrue(all(b['end']-b['start']>=.5 and b['n']>=3 for b in o.blocks))
        o.reset();self.assertEqual(o.block,[])

    def test_real_baseline_source_manifest(self):
        r.verify_sources()


if __name__=='__main__':unittest.main()
