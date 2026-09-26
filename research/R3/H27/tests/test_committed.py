import copy
import hashlib
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import profile,ev,ROOT
from development import compare,source_manifest,synthetic_case,THRESHOLD
from reserve_odometry.core import Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver
from reserve_odometry.committed_disturbance import CommittedDisturbanceObserver


def model(enabled=True,lag=.4):
    c,r=profile()
    return CommittedDisturbanceObserver(c,readout=r,lag_s=lag,threshold=THRESHOLD,enabled=enabled)


def seeded():
    o=model();o.reset(velocity=2.)
    o.step(.9,Sample(.9,.2),Sample(.9,2.),Sample(.9,2.))
    o.disturbance=.2
    h=o._committed_history;h.mode=1
    h.samples.extend([(i/10,.05 if i<7 else .2) for i in range(1,10)])
    return o


class TestCommitted(unittest.TestCase):
    def test_source_identity(self):self.assertEqual(len(source_manifest()['pinned']),18)
    def test_history_exact_copy(self):
        self.assertEqual((ROOT/'research/R3/H27/history.py').read_bytes(),(ROOT/'src/reserve_odometry/reserve_odometry/committed_history.py').read_bytes())
    def test_bad_lag(self):
        with self.assertRaises(ValueError):model(lag=.3)
    def test_bad_threshold(self):
        c,r=profile()
        for threshold in [0,-.1,math.nan,math.inf]:
            with self.assertRaises(ValueError):CommittedDisturbanceObserver(c,readout=r,lag_s=.4,threshold=threshold)
    def test_unchanged_without_history(self):
        o=model();c,r=profile();b=GuardedReadoutObserver(c,readout=r)
        for i in range(100):
            t=i*.05;args=(t,Sample(t,.2),None,None)
            self.assertEqual(o.step(*args),b.step(*args))
    def test_actual_replacement(self):
        o=seeded();e=o.step(1.,Sample(1.,.2),None,None)
        self.assertAlmostEqual(o._committed_d,.05)
        self.assertAlmostEqual(o._committed_applied_da,-.15)
        self.assertAlmostEqual(e.v-o._committed_native_estimate.v,-.015)
        self.assertAlmostEqual(o.disturbance,.2)
    def test_no_duplicate_outage(self):
        o=seeded();o.step(.95,Sample(.95,.2),Sample(.9,2.),Sample(.9,2.))
        self.assertIsNone(o._committed_d)
        self.assertEqual(o._committed_dv,0)
    def test_effect_held_during_loss(self):
        o=seeded();o.step(1.,Sample(1.,.2),None,None);d=o._committed_d
        for i in range(1,20):
            t=1.+i*.05;o.step(t,Sample(t,.2),None,None)
            self.assertEqual(o._committed_d,d)
            self.assertEqual(o.disturbance,.2)
    def test_recovery_keeps_distance(self):
        o=seeded();o.step(1.,Sample(1.,.2),None,None)
        old_ds=o._committed_ds;old_dv=o._committed_dv
        e=o.step(1.05,Sample(1.05,.2),Sample(1.05,2.),Sample(1.05,2.))
        self.assertLess(abs(o._committed_dv),abs(old_dv))
        self.assertNotEqual(o._committed_ds,0)
        self.assertAlmostEqual(o._committed_ds,old_ds+.5*(old_dv+o._committed_dv)*.05)
        self.assertAlmostEqual(e.s,o._committed_native_estimate.s+o._committed_ds)
    def test_command_change_cancels_target_not_distance(self):
        o=seeded();o.step(1.,Sample(1.,.2),None,None);old=o._committed_dv
        o.step(1.05,Sample(1.05,-.1),None,None)
        self.assertIsNone(o._committed_d)
        self.assertAlmostEqual(o._committed_dv,old)
        self.assertNotEqual(o._committed_ds,0)
    def test_stale_cancels_target(self):
        o=seeded();o.step(1.,Sample(1.,.2),None,None)
        o.step(1.05,Sample(0.,.2),None,None)
        self.assertIsNone(o._committed_d)
    def test_future_command_no_target(self):
        o=seeded();o.step(1.,Sample(1.01,.2),None,None)
        self.assertIsNone(o._committed_d)
    def test_reset(self):
        o=seeded();o.step(1.,Sample(1.,.2),None,None);o.reset(position=7.)
        self.assertEqual(o._committed_ds,0);self.assertEqual(o._committed_dv,0)
        self.assertEqual(o.s,7.);self.assertEqual(len(o._committed_history.samples),0)
    def test_integral_and_acceleration(self):
        o=seeded();previous=o.last_estimate
        for i in range(6):
            t=1.+i*.05;e=o.step(t,Sample(t,.2),None,None);dt=e.t-previous.t
            self.assertAlmostEqual(e.s-previous.s,.5*(e.v+previous.v)*dt,places=10)
            self.assertAlmostEqual(e.a,(e.v-previous.v)/dt,places=10)
            previous=e
    def test_clipping_speed_and_no_sign_reversal(self):
        for delta in (-100.,100.):
            o=seeded();o._committed_dv=delta
            e=o.step(1.,Sample(1.,.2),None,None)
            self.assertLessEqual(abs(e.v),o.c.max_speed_mps);self.assertGreater(e.v,0)
    def test_time_error_leaves_state(self):
        o=seeded();state=copy.deepcopy(vars(o))
        with self.assertRaises(ValueError):o.step(.5,Sample(.5,.2))
        self.assertEqual(o.t,state['t']);self.assertEqual(o._committed_ds,state['_committed_ds'])
    def test_off_exact_mixed(self):
        o=model(False);c,r=profile();b=GuardedReadoutObserver(c,readout=r)
        for i in range(2000):
            t=i*.05;u=.2 if i%300<150 else -.2;v=2+.1*math.sin(t)
            wheels=(None,None) if 500<i<570 else (Sample(t,v),Sample(t,v))
            args=(t,Sample(t,u),*wheels)
            self.assertEqual(o.step(*args),b.step(*args))
            for k,value in vars(b).items():self.assertEqual(getattr(o,k),value)
    def test_enabled_all_inner_state_exact(self):
        o=seeded();c,r=profile();b=GuardedReadoutObserver(c,readout=r)
        b.reset(velocity=2.);b.step(.9,Sample(.9,.2),Sample(.9,2.),Sample(.9,2.));b.disturbance=.2
        for i in range(300):
            t=1+i*.05;w=None if i<40 else Sample(t,2.)
            e=o.step(t,Sample(t,.2),w,w);expected=b.step(t,Sample(t,.2),w,w)
            self.assertEqual(o._committed_native_estimate,expected)
            for k,value in vars(b).items():
                if k!='last_estimate':self.assertEqual(getattr(o,k),value)
    def test_prefix(self):
        def run(n):
            o=seeded();out=[]
            for i in range(n):
                t=1+i*.05;w=None if i<40 else Sample(t,2.)
                out.append(o.step(t,Sample(t,.2),w,w))
            return out
        self.assertEqual(run(100),run(200)[:100])
    def test_bounded_long_history(self):
        o=model()
        for i in range(3000):
            t=i*.05;o.step(t,Sample(t,.2),Sample(t,2.),Sample(t,2.))
            self.assertLessEqual(len(o._committed_history.samples),16)
            if o._committed_history.samples:self.assertLessEqual(t-o._committed_history.samples[0][0],1.+1e-9)
    def test_official_scorer_smoke(self):
        events,refs,fault=synthetic_case(.3,.7)
        rows=compare(events,refs,fault)
        self.assertEqual(rows['receivers']['master']['R3_v8']['n'],rows['receivers']['master']['H27_l040']['n'])
        self.assertEqual(rows['activation']['R3_v8']['outputs_sha256'],rows['activation']['H27_off']['outputs_sha256'])
        for metrics in rows['runtime'].values():self.assertEqual(metrics['causal_errors'],0)

if __name__=='__main__':unittest.main()
