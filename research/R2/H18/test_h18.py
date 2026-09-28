import math
from pathlib import Path
import random
import sys
import unittest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src/reserve_odometry'))
from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.outage_uncertainty import OutageUncertaintyObserver
from reserve_odometry.timeline import Timeline


def base_state(o):
    return {k: v for k, v in vars(o).items() if not k.startswith('_h18_')}


class H18Tests(unittest.TestCase):
    def test_disabled_exact_every_baseline_field_and_estimate(self):
        for enabled, pdd in ((False, .04), (True, 0.0)):
            a, b = GuardedReadoutObserver(), OutageUncertaintyObserver(pdd=pdd, enabled=enabled)
            f = r = None
            for i in range(6000):
                t = i*.05
                v = 5 + .4*math.sin(t*.1)
                if i % 2 == 0 and not 1000 <= i < 1300:
                    f = Sample(t, v + (5 if 1800 <= i < 1850 else 0))
                    r = Sample(t, v + (5 if 1800 <= i < 1850 else 0))
                command = Sample(t + (1 if i % 137 == 0 else 0), .1)
                self.assertEqual(a.step(t, command, f, r), b.step(t, command, f, r))
                self.assertEqual(vars(a), base_state(b))

    def test_no_outage_is_exact_mean_and_covariance(self):
        a, b = GuardedReadoutObserver(), OutageUncertaintyObserver(pdd=.04)
        for i in range(1000):
            t = i*.05
            z = Sample(t, 4+.3*math.sin(t/3))
            self.assertEqual(a.step(t, Sample(t, .1), z, z), b.step(t, Sample(t, .1), z, z))
            self.assertEqual(vars(a), base_state(b))

    def test_persistent_outage_matches_analytic_quadratic_variance(self):
        q = .04
        o = OutageUncertaintyObserver(pdd=q)
        o.step(0., Sample(0., 0), Sample(0., 5), Sample(0., 5))
        p0 = o.pv + .25*o.c.process_noise_v
        c0 = math.sqrt(p0*q)
        for i in range(1, 401):
            t = i*.05
            o.step(t, Sample(t, 0))
            h = max(0., t-.25)
            expected = p0 + 2*h*c0 + h*h*q + h*o.c.process_noise_v if h else .01+t*.1
            self.assertAlmostEqual(o.pv, expected, places=10)
            self.assertAlmostEqual(o._h18_pvd, c0+h*q if h else 0., places=10)

    def test_no_wheels_mean_prediction_is_unchanged(self):
        a, b = GuardedReadoutObserver(), OutageUncertaintyObserver(pdd=.04)
        for o in (a,b):
            o.step(0., Sample(0., .1), Sample(0., 5), Sample(0., 5))
        for i in range(1,401):
            t=i*.05
            aa=a.step(t,Sample(t,.1));bb=b.step(t,Sample(t,.1))
            for field in ('v','s','a','disturbance','mode','front_status','rear_status'):
                self.assertEqual(getattr(aa,field),getattr(bb,field))

    def test_joseph_schmidt_psd_and_scalar_identity(self):
        rng=random.Random(18)
        for _ in range(10000):
            p=10**rng.uniform(-7,4);d=10**rng.uniform(-6,0)
            c=rng.uniform(-1,1)*math.sqrt(p*d);r=10**rng.uniform(-5,2)
            k=p/(p+r);post=(1-k)**2*p+k*k*r;cross=(1-k)*c
            self.assertGreaterEqual(post*d-cross*cross, -1e-10)
            self.assertAlmostEqual(post/p,1-k,places=12)
            self.assertAlmostEqual(post*d-cross*cross,
                (1-k)**2*(p*d-c*c)+k*k*r*d,places=9)

    def test_local_finite_difference(self):
        for h in (.05,.2,1.0):
            v,d=3.,.2;eps=1e-6
            f=lambda v,d:v+h*d
            self.assertAlmostEqual((f(v+eps,d)-f(v-eps,d))/(2*eps),1,places=8)
            self.assertAlmostEqual((f(v,d+eps)-f(v,d-eps))/(2*eps),h,places=8)

    def test_return_gain_and_pdd_not_reset(self):
        a,b=GuardedReadoutObserver(),OutageUncertaintyObserver(pdd=.04)
        for o in (a,b):o.step(0.,Sample(0.,.1),Sample(0.,5),Sample(0.,5))
        for i in range(1,101):
            for o in (a,b):o.step(i*.05,Sample(i*.05,.1))
        t=5.05;before=a.pv+.1*.05
        aa=a.step(t,Sample(t,.1),Sample(t,a.v+.1),Sample(t,a.v+.1))
        bb=b.step(t,Sample(t,.1),Sample(t,b.v+.1),Sample(t,b.v+.1))
        self.assertIn(bb.mode,('FUSED','SINGLE_WHEEL'))
        self.assertGreater(b._h18_last_gain,1-a.pv/before)
        self.assertEqual(b._h18_pdd,.04)
        self.assertGreater(b._h18_pvd,0.)

    def test_prefix_causality_future_duplicate_reset(self):
        def events(last):
            rows=[]
            for i in range(last):
                t=i*.05
                rows.extend([(0,Sample(t,.1)),(1,Sample(t,5)),(2,Sample(t,5))])
            return rows
        def run(rows):
            tl=Timeline(OutageUncertaintyObserver(pdd=.04),20,0)
            out=[]
            for ch,s in rows:
                tl.ingest(ch,s)
                out.extend(e for e,_ in tl.advance())
            return out,tl
        short,_=run(events(100));long,tl=run(events(200))
        self.assertEqual(short,long[:len(short)])
        self.assertFalse(tl.ingest(1,Sample(0.,100.)))
        tl.reset()
        self.assertEqual(base_state(tl.observer),vars(GuardedReadoutObserver()))
        o=OutageUncertaintyObserver(pdd=.04)
        e=o.step(0.,Sample(1.,.1),Sample(1.,5),Sample(1.,5))
        self.assertEqual(e.mode,'WAITING_FOR_INITIALIZATION')
        self.assertTrue(e.command_stale)
        self.assertIsNone(o._h18_last_trust)

    def test_zero_lock_and_real_stop(self):
        for speed in (0.,1.5,5.):
            o=OutageUncertaintyObserver(pdd=.04)
            o.reset(velocity=speed)
            for i in range(40):
                t=i*.05;e=o.step(t,Sample(t,0.),Sample(t,0.),Sample(t,0.))
                if speed>=1.5:self.assertNotEqual(e.mode,'STOPPED')
            if speed==0.:self.assertEqual(e.mode,'STOPPED')

    def test_bounded_state_long_mixed_sequence(self):
        o=OutageUncertaintyObserver(pdd=.36)
        keys=set(vars(o))
        for i in range(20000):
            t=i*.05;z=Sample(t,5+.1*math.sin(t)) if i%300<50 else None
            e=o.step(t,Sample(t,.05),z,z)
            self.assertTrue(all(math.isfinite(getattr(e,k)) for k in ('v','s','variance_v','variance_s')))
            self.assertEqual(set(vars(o)),keys)
            self.assertGreaterEqual(o.pv*o._h18_pdd-o._h18_pvd**2,-1e-9)
            self.assertLessEqual(len(o.pair_pending),2)

    def test_invalid_configuration_and_time_do_not_mutate(self):
        for q in (-.01,float('nan'),float('inf'),1.):
            with self.assertRaises(ValueError):OutageUncertaintyObserver(pdd=q)
        o=OutageUncertaintyObserver(pdd=.04);o.step(0.)
        saved=vars(o).copy()
        for t in (0.,-1.,float('nan'),.3):
            with self.assertRaises(ValueError):o.step(t)
            self.assertEqual(vars(o),saved)

if __name__=='__main__':unittest.main()
