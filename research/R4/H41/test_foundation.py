import dataclasses
import json
import math
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import foundation as f

class FoundationTests(unittest.TestCase):
    def test_profile_exact(self):
        c,r=f.profile(); self.assertEqual(c.common_mode_quarantine_s,1.5)
        self.assertEqual(r.holdoff_s,.5); self.assertEqual(c.adaptation_tau_s,.5)
    def test_predict_is_exact_canonical_model_only(self):
        c,r=f.profile(); rng=random.Random(41)
        for _ in range(200):
            o=f.GuardedReadoutObserver(c,readout=r); v=rng.uniform(-20,20)
            a=rng.uniform(-1.,1.);d=rng.uniform(-.6,.6);u=rng.uniform(-1,1);h=rng.uniform(.001,.19)
            o.reset(velocity=v);o.t=0.;o.drive_a=a;o.disturbance=d
            expected=f.predict(o,v,a,d,u,h); got=o.step(h,f.Sample(h,u))
            self.assertEqual(got.v,expected[0]);self.assertEqual(o.drive_a,expected[1])
    def test_stale_future_nan_command_is_neutral(self):
        o=f.GuardedReadoutObserver()
        for cmd in (None,f.Sample(-2.,1),f.Sample(2.,1),f.Sample(0.,float('nan')),f.Sample(0.,2)):
            self.assertEqual(f.effective_u(o,cmd,0),0)
    def test_canonical_offline_replay_not_mutated(self):
        events=[]
        for i in range(200):
            t=i*.05;events.append((t,0,.5 if i%80<40 else -.2))
            if i%2==0:events.extend([(t,1,4.),(t,2,4.)])
        events=f.ev.np.array(events)
        c,r=f.profile(); original=f.ev.Observer
        f.ev.Observer=lambda config:f.GuardedReadoutObserver(config,readout=r)
        try:
            before,meta=f.ev.replay(events,c,f.OPS)
            result=f.probe(events)
            after,meta2=f.ev.replay(events,c,f.OPS)
            self.assertTrue(f.ev.np.array_equal(before,after));self.assertEqual(meta,meta2)
            self.assertEqual(result['outputs'],len(before));self.assertEqual(result['causal_errors'],0)
        finally:f.ev.Observer=original
    def test_role_guard_precedes_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=f.Store(Path(tmp))
            for role in ('test','validation'):
                bag=s.plan['splits'][role][0]
                with patch('sqlite3.connect',side_effect=AssertionError('unexpected IO')):
                    with self.assertRaises(PermissionError):s.load(bag,role)
            with self.assertRaises(PermissionError):s.load(s.plan['splits']['train'][0],'development')
    def test_no_test_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PermissionError):f.obtain_data(Path(tmp),roles=('test',))
    def test_empty_moments_not_zero_error(self):
        self.assertIsNone(f.moments([])['rms'])
    def test_analytic_initial_actuator_sensitivity(self):
        c,r=f.profile();o=f.GuardedReadoutObserver(c,readout=r)
        # Frozen zero target, negligible drag at a high positive speed.
        v0,a0=10.,0.;v1,a1=10.,.1
        for i in range(20):
            v0,a0,_=f.predict(o,v0,a0,0.,0.,.05)
            v1,a1,_=f.predict(o,v1,a1,0.,0.,.05)
        rho=math.exp(-.05/c.actuator_tau_s)
        self.assertAlmostEqual(v1-v0,.1*.05*rho*(1-rho**20)/(1-rho),places=12)

if __name__=='__main__':unittest.main()
