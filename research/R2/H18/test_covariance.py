import copy
import json
import math
from pathlib import Path
import random
import sys
import unittest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src/reserve_odometry'))
from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.outage_covariance import OutageCovarianceObserver
PROFILE = json.loads((ROOT/'src/reserve_odometry/config/guarded_readout_v7.json').read_text())


def make(cls=OutageCovarianceObserver, **kw):
    return cls(Config(**PROFILE['config']), readout=ReadoutConfig(**PROFILE['readout']), **kw)


class CovarianceTests(unittest.TestCase):
    def test_parameter_bounds(self):
        for x in (float('nan'), float('inf'), -1, 0, .37):
            with self.assertRaises(ValueError): make(disturbance_variance=x)
        with self.assertRaises(ValueError): make(enabled=1)

    def test_disabled_exact_all_base_fields_6000_steps(self):
        a,b=make(GuardedReadoutObserver),make(enabled=False)
        rng=random.Random(182026)
        for i in range(6000):
            t=i*.05; v=5+math.sin(t/10)
            f=Sample(t,v);r=Sample(t,v+.01*rng.random())
            if i%500 in range(200,300): f=r=None
            if i%501==10:f=r=Sample(t,0)
            if i%502==30:f=r=Sample(t,20)
            args=(t,Sample(t,.1*math.sin(t)),f,r)
            self.assertEqual(a.step(*args),b.step(*args))
            for key,value in vars(a).items():self.assertEqual(value,getattr(b,key),key)

    def test_no_outage_mean_and_state_equivalence(self):
        a,b=make(GuardedReadoutObserver),make(enabled=True,disturbance_variance=.1)
        for i in range(1000):
            t=i*.05;w=Sample(t,5+.1*math.sin(t));args=(t,Sample(t,.1),w,w)
            self.assertEqual(a.step(*args),b.step(*args))
            for k,v in vars(a).items():self.assertEqual(v,getattr(b,k),k)
        self.assertEqual(b.h18_episodes,0)

    def test_outage_mean_unchanged_variance_grows(self):
        a,b=make(GuardedReadoutObserver),make(enabled=True,disturbance_variance=.1)
        for i in range(200):
            t=i*.05;w=Sample(t,5) if i<50 else None
            x,y=a.step(t,Sample(t,.1),w,w),b.step(t,Sample(t,.1),w,w)
            for k in ('v','s','a','disturbance','mode','front_status','rear_status'):
                self.assertEqual(getattr(x,k),getattr(y,k),k)
        self.assertGreater(b.pv,a.pv)
        self.assertGreater(b.h18_active_ticks,100)

    def test_constant_bias_closed_form(self):
        o=make(enabled=True,disturbance_variance=.1);o.reset(velocity=5)
        o.step(0,Sample(0,0));o.h18_active=True;o.h18_pdd=.2;o.h18_pvd=.03;o.pv=.5
        for i in range(1,21):o.step(i*.05,Sample(i*.05,0))
        self.assertAlmostEqual(o.pv,.5+2*.03+.2+.1,places=11)
        self.assertAlmostEqual(o.h18_pvd,.03+.2,places=11)
        self.assertAlmostEqual(o.h18_pdd,.2,places=11)

    def test_joseph_and_unknown_correlation_envelope(self):
        rng=random.Random(18)
        for _ in range(2000):
            p,d,r=[10**rng.uniform(-4,1) for _ in range(3)]
            c=rng.uniform(-1,1)*math.sqrt(p*d);k=p/(p+r)
            post=(1-k)**2*p+k*k*r;cross=(1-k)*c
            self.assertGreaterEqual(post*d-cross*cross,-1e-10)
            self.assertGreaterEqual(p*d-c*c,-1e-10)
            self.assertAlmostEqual(post,p*r/(p+r),places=11)

    def test_local_transition_finite_difference(self):
        for dt in (.01,.05,.2):
            eps=1e-6;v,d=3.,.2
            dv=((v+eps+dt*d)-(v-eps+dt*d))/(2*eps)
            dd=((v+dt*(d+eps))-(v+dt*(d-eps)))/(2*eps)
            self.assertAlmostEqual(dv,1,places=8);self.assertAlmostEqual(dd,dt,places=8)

    def test_psd_finite_and_constant_memory_20000_steps(self):
        o=make(enabled=True,disturbance_variance=.36);keys=set(vars(o))
        for i in range(20000):
            t=i*.05;w=Sample(t,5+.2*math.sin(t)) if i%300<80 else None
            e=o.step(t,Sample(t,.1),w,w)
            self.assertTrue(all(math.isfinite(x) for x in (e.v,e.s,e.variance_v,e.variance_s,o.h18_pvd,o.h18_pdd)))
            if o.h18_active:self.assertGreaterEqual(o.pv*o.h18_pdd-o.h18_pvd**2,-1e-7)
            self.assertEqual(set(vars(o)),keys)
            self.assertEqual(len(o.used),2);self.assertEqual(len(o.raw_previous),2)
        self.assertGreater(o.h18_episodes,20)

    def test_prefix_and_future_inputs(self):
        a,b=make(enabled=True),make(enabled=True)
        for i in range(100):
            t=i*.05;w=Sample(t,5) if i<20 else None
            self.assertEqual(a.step(t,Sample(t,0),w,w),b.step(t,Sample(t,0),w,w))
        past=copy.deepcopy(a.last_estimate)
        a.step(5.,Sample(6.,1),Sample(6.,30),Sample(6.,30))
        b.step(5.,None,None,None)
        self.assertEqual(a.last_estimate,b.last_estimate)
        self.assertEqual(past.t,4.95)

    def test_duplicates_not_reassimilated(self):
        o=make(enabled=True);w=Sample(0,5)
        o.step(0,Sample(0,0),w,w)
        e=o.step(.05,Sample(.05,0),w,w)
        self.assertEqual(e.front_status,'DUPLICATE_OR_OLD');self.assertEqual(o.h18_last_gain,0)

    def test_invalid_time_is_transactional(self):
        o=make(enabled=True);o.step(1,Sample(1,0),Sample(1,5),Sample(1,5))
        for t in (1,.5,2,float('nan')):
            old=copy.deepcopy(vars(o))
            with self.assertRaises(ValueError):o.step(t)
            self.assertEqual(vars(o),old)

    def test_reset_clears_covariance(self):
        o=make(enabled=True);o.step(0,Sample(0,0),Sample(0,5),Sample(0,5))
        for i in range(1,40):o.step(i*.05,Sample(i*.05,0))
        self.assertTrue(o.h18_active);o.reset()
        self.assertFalse(o.h18_active);self.assertEqual(o.h18_episodes,0)
        self.assertEqual(o.pv,1);self.assertEqual(o.h18_pvd,0);self.assertEqual(o.h18_pdd,0)

    def test_guards_inherited_unchanged_and_zero_lock(self):
        for name in ('_wheel','_reacquire_pair','_take_pending_pair','drive_target','resistance'):
            self.assertIs(getattr(OutageCovarianceObserver,name),getattr(Observer,name))
        o=make(enabled=True);o.step(0,Sample(0,0),Sample(0,1.5),Sample(0,1.5))
        for i in range(1,15):
            t=i*.05;e=o.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
            self.assertNotEqual(e.mode,'STOPPED');self.assertNotEqual(e.front_status,'ACCEPTED')

if __name__=='__main__': unittest.main()
