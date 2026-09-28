"""Implementation tests, not real-data accuracy evidence."""
import copy
import inspect
import math
from pathlib import Path
import random
import sys
import unittest
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[3]/'src/reserve_odometry')]
from common import profile, alternate, baseline, score, np, ev, Sample, Config
from outage_physics import OutagePhysicsObserver, Rollout


def factory(enabled=True):
    return OutagePhysicsObserver(profile()[0],alternate(),readout=profile()[1],enabled=enabled)


def feed(o, begin=0, end=600, outage=(100,260), u=.1):
    out=[]
    for i in range(begin,end):
        t=i*.05;wheel=None if outage[0]<=i<outage[1] else Sample(t,4.)
        cmd=Sample(t,u(t) if callable(u) else u)
        out.append(o.step(t,cmd,wheel,wheel))
    return out


class H23Tests(unittest.TestCase):
    def test_profile_not_defaults(self):
        c,r=profile();self.assertEqual(c.common_mode_quarantine_s,1.5)
        self.assertEqual(r.gain,1.);self.assertNotEqual(c.max_power_w,Config().max_power_w)
    def test_healthy_exact(self):
        b=baseline();c=factory()
        for i in range(300):
            t=i*.05;args=(t,Sample(t,.1),Sample(t,4.),Sample(t,4.))
            self.assertEqual(b.step(*args),c.step(*args));self.assertEqual(vars(b),vars(c.inner))
        self.assertEqual(c.delta_s,0.)
    def test_disabled_full_state(self):
        b=baseline();c=factory(False);rng=random.Random(23)
        for i in range(2000):
            t=i*.05;bad=(i%500)>350;v=4.+.1*math.sin(t)
            f=None if bad else Sample(t-.01,v)
            r=None if bad else Sample(t-.02,v+.005*rng.random())
            args=(t,Sample(t,.05),f,r)
            self.assertEqual(b.step(*args),c.step(*args));self.assertEqual(vars(b),vars(c.inner))
    def test_enabled_all_inner_fields(self):
        c=factory();b=baseline()
        for i in range(2000):
            t=i*.05;v=Sample(t,4.) if i%400<160 else None
            args=(t,Sample(t,.1 if i%200<100 else -.1),v,v)
            b.step(*args);c.step(*args);self.assertEqual(vars(b),vars(c.inner))
    def test_activation_and_five_second_limit(self):
        c=factory();feed(c,end=110);self.assertIsNotNone(c.rollout)
        start=c.started_at;feed(c,begin=110,end=250)
        self.assertEqual(c.started_at,start);self.assertIsNone(c.rollout);self.assertTrue(c.blocked)
    def test_acceleration_continuity(self):
        c=factory()
        for i in range(200):
            t=i*.05;w=Sample(t,4.) if i<80 else None;before=c.rollout
            e=c.step(t,Sample(t,.1),w,w)
            if before is None and c.rollout is not None:
                a=c.inner.drive_a-c.inner.resistance(c.inner.v)+c.inner.disturbance
                b=c.rollout.drive_a-c.rollout.resistance(c.rollout.v)+c.rollout.disturbance
                self.assertAlmostEqual(a,b,14);self.assertEqual(c.delta_v,0.);return
        self.fail('No activation')
    def test_no_disturbance_training_in_outage(self):
        c=factory();feed(c,end=120);self.assertIsNotNone(c.rollout)
        d=c.rollout.disturbance;feed(c,begin=120,end=145)
        self.assertEqual(c.rollout.disturbance,d)
    def test_offset_fallback(self):
        c=factory();feed(c,end=100,outage=(1000,1001))
        c.inner.disturbance=-c.c.disturbance_limit_mps2
        feed(c,begin=100,end=130,outage=(100,400),u=0.)
        self.assertIsNone(c.rollout);self.assertEqual(c.delta_v,0.)
        self.assertEqual(c.phase,'FALLBACK_OFFSET')
    def test_distance_release_persists(self):
        c=factory();prev=None;integ=0.
        for i in range(400):
            t=i*.05;w=None if 100<=i<170 else Sample(t,4.)
            old=c.delta_v;old_t=c.t;e=c.step(t,Sample(t,.1),w,w)
            if old_t is not None:integ+=.5*(old+c.delta_v)*(t-old_t)
            self.assertAlmostEqual(e.s-c.inner.last_estimate.s,integ,10)
            if i==169:previous_s=c.delta_s;self.assertNotEqual(previous_s,0.)
        self.assertEqual(c.delta_v,0.);self.assertNotEqual(c.delta_s,0.)
        self.assertAlmostEqual(c.delta_s,integ,12)
    def test_bounded_release(self):
        c=factory();feed(c,end=169);old=c.delta_v
        self.assertNotEqual(old,0.)
        e=c.step(169*.05,Sample(169*.05,.1),Sample(169*.05,4.),Sample(169*.05,4.))
        self.assertLessEqual(abs(c.delta_v-old),c.c.reacquire_step_mps/.1*.05+1e-12)
    def test_command_change_and_stale_abort(self):
        c=factory();feed(c,end=125);old=c.rollout.drive_a
        feed(c,begin=125,end=135,u=-.3)
        self.assertIsNotNone(c.rollout);self.assertNotEqual(c.rollout.drive_a,old)
        t=135*.05;c.step(t,Sample(t-1.,.4),None,None)
        self.assertIsNone(c.rollout);self.assertTrue(c.blocked)
    def test_future_duplicates_causality(self):
        c=factory();b=baseline()
        for i in range(200):
            t=i*.05;w=Sample(t+1,4.) if i>100 else Sample((i//2)*.1,4.)
            args=(t,Sample(t,.1),w,w);b.step(*args);c.step(*args)
            self.assertEqual(vars(b),vars(c.inner))
            if c.last_trusted is not None:self.assertLessEqual(c.last_trusted,t+1e-9)
    def test_prefix(self):
        a=factory();b=factory();x=feed(a,end=180);y=feed(b,end=180)
        feed(a,begin=180,end=300,u=-.2);feed(b,begin=180,end=300,u=.6)
        self.assertEqual(x,y)
    def test_reset_and_invalid_time(self):
        c=factory();feed(c,end=170);self.assertNotEqual(c.delta_s,0.)
        state=(c.t,c.delta_s,c.delta_v,c.started_at)
        with self.assertRaises(ValueError):c.step(c.t-1.)
        self.assertEqual(state,(c.t,c.delta_s,c.delta_v,c.started_at))
        with self.assertRaises(ValueError):c.step(c.t+1.)
        c.reset(velocity=2.,position=7.);self.assertEqual(c.delta_s,0.);self.assertIsNone(c.rollout)
        self.assertEqual(c.inner.s,7.)
    def test_true_stop_and_common_mode_quarantine(self):
        c=factory();b=baseline()
        for i in range(500):
            t=i*.05;v=0. if i<100 else 4. if i<300 else 9.
            args=(t,Sample(t,0.),Sample(t,v),Sample(t,v));b.step(*args);e=c.step(*args)
            self.assertEqual(vars(b),vars(c.inner))
            if e.mode=='STOPPED':self.assertEqual(e.v,0.)
            if t<c.inner.reacquire_blocked_until:self.assertIsNone(c.rollout)
    def test_bounds_and_constant_memory(self):
        c=factory();slots=tuple(c.__slots__)
        for i in range(15000):
            t=i*.05;w=Sample(t,4.) if i%400<100 else None
            e=c.step(t,Sample(t,.5*math.sin(t)),w,w)
            self.assertLessEqual(abs(c.delta_v),.75+1e-12);self.assertLessEqual(abs(e.v),40.)
            self.assertTrue(all(math.isfinite(v) for v in (e.v,e.s,e.a,e.variance_v,e.variance_s)))
            if c.rollout:self.assertLessEqual(abs(c.rollout.disturbance),.6)
        self.assertEqual(tuple(c.__slots__),slots);self.assertFalse(hasattr(c,'__dict__'))
        self.assertNotIn('numpy',inspect.getsource(sys.modules[OutagePhysicsObserver.__module__]))
    def test_missing_reference(self):
        es=np.array([(i*.05,ch,0. if ch==0 else 4.) for i in range(20) for ch in range(3)])
        row=score(es,{'master':[],'rover':[]},{'baseline_v2':baseline,'balanced_physics':baseline})
        self.assertIsNone(row['receivers']['master']['baseline_v2']['rmse'])
        self.assertNotIn('mae',row['receivers']['master']['baseline_v2'])
    def test_no_oracle_signature(self):
        self.assertEqual(list(inspect.signature(OutagePhysicsObserver.step).parameters),['self','t','command','front','rear'])

    def test_low_speed_zero_lock(self):
        c=factory();b=baseline()
        for i in range(250):
            t=i*.05;v=1.5 if i<80 or i>140 else 0.
            args=(t,Sample(t,.1),Sample(t,v),Sample(t,v));x=b.step(*args);y=c.step(*args)
            self.assertEqual(vars(b),vars(c.inner))
            if 85<i<140:
                self.assertNotEqual(y.mode,'STOPPED');self.assertGreater(y.v,0.)
    def test_same_physics_limit(self):
        c=OutagePhysicsObserver(profile()[0],profile()[0],readout=profile()[1]);b=baseline()
        for i in range(400):
            t=i*.05;w=Sample(t,4.) if i<80 or i>230 else None
            args=(t,Sample(t,.1),w,w);x=b.step(*args);y=c.step(*args)
            self.assertAlmostEqual(x.v,y.v,12);self.assertAlmostEqual(x.s,y.s,10)
    def test_latest_trusted_never_regresses(self):
        c=factory();last=-math.inf
        for i in range(100):
            t=i*.05;f=Sample(t-.01,4.);r=Sample(t-.04,4.)
            c.step(t,Sample(t,.1),f,r)
            if c.last_trusted is not None:
                self.assertGreaterEqual(c.last_trusted,last);last=c.last_trusted

if __name__=='__main__':unittest.main(verbosity=2)
