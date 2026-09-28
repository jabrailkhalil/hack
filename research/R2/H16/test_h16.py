"""H16 tests use canonical v7; optional candidate file exercises enabled physics."""
from dataclasses import asdict
import inspect
import json
import math
import os
from pathlib import Path
import unittest
from unittest import mock
import numpy as np
import run as h
CANDIDATE=os.getenv('H16_CANDIDATE_FILE')
THETA=np.array(json.loads(Path(CANDIDATE).read_text())['theta']) if CANDIDATE else h.THETA0*np.array([1.03,.97,1.02,1.01,1.,1.01,1.02])

def samples(i):
    t=i*.05;st=(i//2)*.1;speed=2.+.15*math.sin(st)
    return t,(h.Sample(st,.05),h.Sample(st,speed),h.Sample(st,speed))

class H16Tests(unittest.TestCase):
    def test_source_integrity(self):self.assertEqual(h.check_integrity()['baseline'],h.BASE)
    def test_disabled_entire_state(self):
        base=h.GuardedReadoutObserver(h.base_config(),readout=h.ReadoutConfig(1.,.5));off=h.observer(THETA,enabled=False)
        for i in range(1200):
            t,args=samples(i)
            if 300<i<340:args=(args[0],None,None)
            if i==500:args=(args[0],h.Sample(t+1,8.),h.Sample(t+1,8.))
            if i==600:base.reset();off.reset()
            self.assertEqual(base.step(t,*args),off.step(t,*args));self.assertEqual(base.__dict__,off.__dict__)
    def test_only_seven_fields_change(self):
        a,b=asdict(h.base_config()),asdict(h.config_for(THETA));self.assertTrue(all(a[k]==b[k] for k in a if k not in h.PHYSICAL))
    def test_config_mapping_and_bounds(self):
        np.testing.assert_allclose(h.theta_from(h.config_for(THETA)),THETA,rtol=1e-14,atol=1e-18)
        for bad in (h.LOW-1,h.HIGH+1,np.full(7,np.nan)):
            with self.assertRaises(ValueError):h.config_for(bad)
    def test_role_denied_before_io(self):
        s=h.Store();test=s.plan['splits']['test'][0];train=s.plan['splits']['train'][0]
        with mock.patch.object(h.sqlite3,'connect',side_effect=AssertionError('SQL reached')):
            for bag,role in [(test,'test'),(test,'train'),(train,'development')]:
                with self.assertRaises(PermissionError):s.load(bag,role)
    def test_causal_prefix_and_input_nonmutation(self):
        inp=[samples(i) for i in range(160)];a,b=h.observer(THETA),h.observer(THETA)
        ea=[a.step(t,*args) for t,args in inp[:100]];eb=[b.step(t,*args) for t,args in inp]
        self.assertEqual(ea,eb[:100]);self.assertEqual(inp,[samples(i) for i in range(160)])
    def test_future_duplicate_stale_reset(self):
        o=h.observer(THETA);o.reset(velocity=2.)
        e=o.step(0,h.Sample(1,.5),h.Sample(1,2.),h.Sample(1,2.));self.assertTrue(e.command_stale);self.assertEqual(o.used,[None,None])
        o.step(.05,h.Sample(.05,0.),h.Sample(.05,2.),h.Sample(.05,2.))
        e=o.step(.1,h.Sample(.05,0.),h.Sample(.05,2.),h.Sample(.05,2.));self.assertEqual(e.front_status,'DUPLICATE_OR_OLD')
        for i in range(3,20):e=o.step(i*.05)
        self.assertTrue(e.command_stale);o.reset();fresh=h.observer(THETA);self.assertEqual(o.__dict__,fresh.__dict__)
    def test_zero_lock_does_not_assimilate_low_speed(self):
        o=h.observer(THETA);o.reset(velocity=1.5)
        for i in range(8):
            t=i*.05;e=o.step(t,h.Sample(t,0.),h.Sample(t,0.),h.Sample(t,0.))
            self.assertNotEqual(e.mode,'STOPPED');self.assertNotEqual(e.front_status,'ACCEPTED')
        self.assertGreater(e.v,.5)
    def test_true_stationary(self):
        o=h.observer(THETA)
        for i in range(80):
            t=i*.05;e=o.step(t,h.Sample(t,0.),h.Sample(t,0.),h.Sample(t,0.))
        self.assertEqual(e.v,0.);self.assertEqual(e.s,0.)
    def test_no_nan_and_no_new_history(self):
        o=h.observer(THETA);keys=set(o.__dict__)
        for i in range(400):
            t,args=samples(i)
            if i%17==0:args=(h.Sample(t,float('nan')),None,h.Sample(t,float('inf')))
            e=o.step(t,*args)
            self.assertTrue(all(math.isfinite(x) for x in (e.v,e.s,e.disturbance,e.variance_v)))
            self.assertLessEqual(abs(e.v),o.c.max_speed_mps);self.assertLessEqual(abs(e.disturbance),o.c.disturbance_limit_mps2)
        self.assertEqual(keys,set(o.__dict__));self.assertTrue(all(len(v)<=2 for v in o.__dict__.values() if isinstance(v,list)))
    def make_window(self):
        warm=[samples(i) for i in range(101)];anchor=warm[-1][0];ts=anchor+np.arange(1,101)*.05
        commands=[h.Sample(float(t),.1 if j<40 else -.2 if j<70 else 0.) for j,t in enumerate(ts)]
        return h.Window('synthetic','g','traction',anchor,warm,ts,commands,np.array([3.,3.,3.]))
    def test_vectorized_rollout_matches_runtime(self):
        w=self.make_window()
        for theta in (h.THETA0,THETA):np.testing.assert_allclose(h.predict_windows(theta,[w])[0],h.original_rollout(theta,w),atol=1e-10,rtol=0)
    def test_rollout_never_reads_pseudo_target(self):
        w=self.make_window();p=h.predict_windows(THETA,[w]);w.target=np.full(3,999.)
        np.testing.assert_array_equal(h.predict_windows(THETA,[w]),p);signature=inspect.signature(h.rollout_from_states)
        self.assertNotIn('target',signature.parameters);self.assertNotIn('wheels',signature.parameters)
    def test_loss_normalizations(self):
        r=np.array([0.,1.,100.]);z=r*np.sqrt(2/(np.sqrt(1+r*r)+1))
        np.testing.assert_allclose(z*z,2*(np.sqrt(1+r*r)-1),atol=1e-13);np.testing.assert_array_equal(h.SIGMA,[.2,.5,1.1])
    def test_group_partition_does_not_split_related_bags(self):
        s=h.Store();groups=sorted({r['group'] for r in s.records.values() if r['split']=='train'});check=set(groups[::4]);fit=set(groups)-check
        self.assertFalse(check&fit);self.assertEqual(len(groups),27)
    def test_fixed_zero_guard(self):
        self.assertFalse(h.gt(1e-13,0,.005));self.assertTrue(h.gt(1e-9,0,.005))
if __name__=='__main__':unittest.main()
