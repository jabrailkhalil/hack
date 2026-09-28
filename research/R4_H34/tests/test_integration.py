import dataclasses
import hashlib
import importlib.util
import math
from pathlib import Path
import random
import sys
import unittest
R=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(R/'tools/research_R4_H34'))
from common import make, norm, profile, Sample, DiscretizationObserver
from reserve_odometry.integration_h34 import integrate, mean_fraction
hp=R/'research/R4_H34/historical/numerics_h08.py'
sp=importlib.util.spec_from_file_location('historical_h08',hp);old=importlib.util.module_from_spec(sp);sp.loader.exec_module(old)

class IntegrationTests(unittest.TestCase):
    def test_historical_blob(self):
        b=hp.read_bytes();self.assertEqual(hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),'9fa1bbdbc052c9c93fc15426e8c37b4b38e1f61f')
    def test_h08_kernel_exact(self):
        rng=random.Random(34)
        for i in range(3000):
            dt=rng.choice([0.,1e-12,.05,.1,.2]);tau=rng.uniform(.05,3)
            d,v,q,dist=rng.uniform(-3,3),rng.uniform(-39,39),rng.uniform(-3,3),rng.uniform(-.6,.6)
            res=lambda x:.05*math.tanh(x/.2)+.0001*x*abs(x)
            a=integrate(dt,tau,d,v,q,dist,res,3,40);b=old.predict(dt,tau,d,v,q,dist,res,3,40)
            self.assertEqual((a[0],a[2]),b)
    def test_exact_integral_high_precision(self):
        from decimal import Decimal,localcontext
        with localcontext() as ctx:
            ctx.prec=65
            for val in (0.,1e-14,1e-10,1e-6,1e-4,.1,1.,4.):
                x=Decimal(str(val));expected=0. if not val else float(1-(1-(-x).exp())/x)
                self.assertAlmostEqual(mean_fraction(val),expected,delta=2e-16)
    def test_constant_target(self):
        for dt in (0.,1e-12,.05,.2):
            end,a,v=integrate(dt,.4,.3,5,.3,0,lambda v:0,3,40)
            self.assertEqual(end,.3);self.assertEqual(a,.3);self.assertEqual(v,5+dt*.3)
    def test_zero_dt(self):
        self.assertEqual(integrate(0,.4,.3,5,1,0,lambda v:.1,3,40),(0.3,0.19999999999999998,5))
    def test_invalid_time(self):
        for dt,tau in [(-1,.4),(math.nan,.4),(.05,0),(.05,math.inf)]:
            with self.assertRaises(ValueError):integrate(dt,tau,0,0,0,0,lambda x:0,3,40)
    def test_midpoint_resistance(self):
        seen=[]
        def resistance(v):seen.append(v);return .02*v
        _,_,v=integrate(.05,.4,.2,5,1,0,resistance,3,40)
        self.assertEqual(len(seen),2);self.assertNotEqual(seen[0],seen[1]);self.assertGreater(v,5)
    def test_off_complete_state_equivalence(self):
        a,b=make('baseline'),make('A');rng=random.Random(34)
        f=r=None
        for i in range(6000):
            t=i*.05;cmd=Sample(t,.6*math.sin(t*.07))
            if i%2==0:
                val=5+math.sin(t*.13); f=Sample(t,val+rng.gauss(0,.02));r=Sample(t,val+rng.gauss(0,.02))
                if i%301<20:f=r=None
                if i%401==100:f=r=Sample(t,0)
                if i%501==100:f=r=Sample(t,10)
            x,y=a.step(t,cmd,f,r),b.step(t,cmd,f,r)
            self.assertEqual(norm(x),norm(y))
            for k,v in vars(a).items():self.assertEqual(norm(v),norm(getattr(b,k)),k)
    def test_readout_actual_acceleration(self):
        b=make('B');b.reset(velocity=5);b.step(0,Sample(0,1),Sample(0,5),Sample(0,5))
        for i in range(1,40):
            t=i*.05;b.step(t,Sample(t,1),Sample(t-.02,5),Sample(t-.02,5))
            self.assertEqual(b._readout_acceleration_h34(100,100),b._effective_acceleration_h34)
    def test_future_not_used(self):
        a,b=make('B'),make('B');a.reset(velocity=5);b.reset(velocity=5)
        self.assertEqual(a.step(0,Sample(1,1),Sample(1,20),Sample(1,20)),b.step(0))
    def test_prefix_causality(self):
        a,b=make('B'),make('B')
        for i in range(200):
            t=i*.05;z=5+math.sin(t)
            x=a.step(t,Sample(t,.2),Sample(t,z),Sample(t,z));y=b.step(t,Sample(t,.2),Sample(t,z),Sample(t,z))
            self.assertEqual(x,y)
        b.step(10,Sample(10,-1),Sample(10,40),Sample(10,40));self.assertEqual(a.t,199*.05)
    def test_duplicate_no_cov_update(self):
        b=make('B');b.step(0,Sample(0,0),Sample(0,5),Sample(0,5));p=b.pv
        e=b.step(.05,Sample(0,0),Sample(0,5),Sample(0,5));self.assertGreater(b.pv,p);self.assertEqual(e.front_status,'DUPLICATE_OR_OLD')
    def test_zero_lock(self):
        b=make('B');b.reset(velocity=1.5)
        for i in range(41):
            t=i*.05;e=b.step(t,Sample(t,1),Sample(t,0),Sample(t,0));self.assertNotEqual(e.mode,'STOPPED')
    def test_common_quarantine(self):
        b=make('B')
        for i in range(61):
            t=i*.05;z=10 if 1<=t<2.2 else 5
            e=b.step(t,Sample(t,0),Sample(t,z),Sample(t,z))
            if 1<=t<2.2:self.assertNotEqual(e.mode,'REACQUIRING')
    def test_true_stop(self):
        b=make('B')
        for i in range(50):
            t=i*.05;e=b.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
        self.assertEqual(e.mode,'STOPPED');self.assertEqual(e.s,0)
    def test_reset_and_gap(self):
        b=make('B');b.step(0)
        with self.assertRaises(ValueError):b.step(1)
        b.reset();self.assertEqual(b._effective_acceleration_h34,0);b.step(1)
    def test_signed_braking_no_reversal(self):
        b=make('B');b.reset(velocity=-.2)
        for i in range(200):
            old_v=b.v
            e=b.step(i*.05,Sample(i*.05,-1));self.assertGreaterEqual(old_v*e.v,0)
    def test_constant_memory_bounds_distance(self):
        b=make('B');b.reset(velocity=5);keys=set(vars(b));last=None
        for i in range(12000):
            t=i*.05; e=b.step(t,Sample(t,.1))
            self.assertEqual(set(vars(b)),keys);self.assertLessEqual(abs(e.v),40);self.assertLessEqual(abs(e.disturbance),.6)
            if last:self.assertAlmostEqual(e.s-last.s,.025*(last.v+e.v),delta=1e-9)
            last=e
    def test_scheme_rejection(self):
        with self.assertRaises(ValueError):DiscretizationObserver(scheme='C')

if __name__=='__main__':unittest.main()
