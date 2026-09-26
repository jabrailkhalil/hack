"""H41 executable structural/numerical checks, not real-data accuracy evidence."""
import dataclasses
import importlib
import math
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import foundation as f
import runtime
import numpy as np
C=runtime.candidate_class()
m=importlib.import_module(C.__module__)


def norm(x):
    if dataclasses.is_dataclass(x):return dataclasses.asdict(x)
    if isinstance(x,(list,tuple)):return [norm(y) for y in x]
    if isinstance(x,dict):return {k:norm(v) for k,v in x.items()}
    return x


def make(enabled=True,scale=1.):
    c,r=f.profile();return C(c,readout=r,enabled=enabled,synthetic_scale=scale)


def state_equal(test,base,other):
    for key,value in vars(base).items():
        test.assertEqual(norm(value),norm(getattr(other,key)),key)


class JointTests(unittest.TestCase):
    def test_disabled_exact_6000_ticks_all_baseline_fields(self):
        b=f.GuardedReadoutObserver(*[f.profile()[0]],readout=f.profile()[1]);o=make(False)
        rng=random.Random(41001)
        for i in range(6000):
            t=i*.05;ts=(i//2)*.1
            u=.4 if i%600<200 else (-.3 if i%600>400 else 0.)
            z=4+.1*math.sin(ts)
            front=None if i%400>300 else f.Sample(ts,z)
            rear=f.Sample(ts,z+.003) if i%500<450 else None
            if i%311==0:front=f.Sample(t+1,30.)
            if i%821==0:front=f.Sample(ts,float('nan'))
            args=(t,f.Sample(ts,u),front,rear)
            self.assertEqual(norm(b.step(*args)),norm(o.step(*args)))
            state_equal(self,b,o)

    def test_jacobian_1000_independent_finite_differences(self):
        o=make();rng=random.Random(41002);mx=0.;count=0
        for direction in (-1.,1.):
            o.c.travel_direction=direction
            for _ in range(500):
                u=rng.uniform(-1,1);v=rng.choice((-1,1))*rng.uniform(.35,38)
                aa=rng.uniform(-1.1,1.1);d=rng.uniform(-.6,.6);h=rng.uniform(.005,.2)
                vp,ap,_=f.predict(o,v,aa,d,u,h)
                F,_=m.jacobian(o.c,u,v,ap,d,h)
                J=[];eps=1e-5
                for dv,da in ((eps,0.),(0.,eps)):
                    plus=np.array(f.predict(o,v+dv,aa+da,d,u,h)[:2])
                    minus=np.array(f.predict(o,v-dv,aa-da,d,u,h)[:2])
                    J.append((plus-minus)/(2*eps))
                error=float(np.max(abs(np.array(F).reshape(2,2)-np.array(J).T)))
                mx=max(mx,error);count+=1
                self.assertLess(error,2e-7)
        print('JACOBIAN_CASES',count,'MAX_ABS',mx)

    def test_projection_rows_saturation_and_sign(self):
        o=make()
        for v,aa,d,u,h in ((39.99,20.,0.,1.,.1),(.01,-1.,0.,-.5,.1),(-.01,1.,0.,-.5,.1)):
            F,L=m.jacobian(o.c,u,v,aa,d,h)
            self.assertEqual(F[:2],(0.,0.));self.assertEqual(L,0.)
        F,L=m.jacobian(o.c,1.,4.,20.,0.,.1)
        self.assertEqual(F[0],1.);self.assertEqual(F[1],0.);self.assertEqual(L,0.)

    def test_joseph_matrix_psd_5000_constrained_cases(self):
        rng=np.random.default_rng(41003);maximum=0.
        for i in range(5000):
            M=rng.normal(size=(2,2));P=M@M.T*.2;r=float(rng.uniform(.001,1.))
            kv=float(P[0,0]/(P[0,0]+r));ka=float(P[1,0]/(P[0,0]+r))
            ka=0. if i%3==0 else (ka*.1 if i%3==1 else ka)
            K=np.array([[kv],[ka]]);A=np.eye(2)-K@np.array([[1.,0.]])
            expected=A@P@A.T+K@K.T*r
            p,c,a=m.joseph(P[0,0],P[0,1],P[1,1],kv,ka,r)
            actual=np.array([[p,c],[c,a]])
            maximum=max(maximum,float(np.max(abs(expected-actual))))
            self.assertTrue(np.allclose(expected,actual,rtol=1e-12,atol=1e-14))
            self.assertGreaterEqual(float(np.linalg.eigvalsh(actual)[0]),-1e-12)
        print('JOSEPH_CASES',5000,'MAX_ABS',maximum)

    def test_psd_bounded_state_and_synthetic_scales(self):
        for scale in (.5,1.,2.):
            o=make(scale=scale);keys=None
            for i in range(10000):
                t=i*.05;ts=(i//2)*.1;u=.6 if i%1000<500 else -.4
                z=5.+math.sin(ts*.2)
                wheels=(None,None) if i%600>=450 else (f.Sample(ts,z),f.Sample(ts,z))
                if i%751==0:wheels=(f.Sample(ts,float('nan')),None)
                e=o.step(t,f.Sample(ts,u),*wheels)
                self.assertTrue(all(math.isfinite(x) for x in (e.v,e.s,e.a,e.variance_v,e.variance_s,o.h41_paa,o.h41_pva)))
                self.assertLessEqual(abs(o.drive_a),m.drive_bound(o.c)+1e-12)
                self.assertGreaterEqual(o.pv*o.h41_paa-o.h41_pva**2,-1e-12)
                self.assertLessEqual(o.h41_paa,m.drive_bound(o.c)**2+1e-12)
                self.assertLessEqual(o.pv,o.c.max_speed_mps**2+1e-12)
                if keys is None:keys=set(vars(o))
                self.assertEqual(keys,set(vars(o)))
                self.assertEqual(len(o.raw_previous),2)
                self.assertFalse(any(isinstance(x,list) and len(x)>2 for x in vars(o).values()))

    def test_direct_correction_preserves_d_and_zero_Ka(self):
        o=make();o.reset(velocity=4);o.disturbance=.123;o.h41_pva=.1;o.h41_paa=.2
        o.pv=.3;oldA=o.drive_a
        o._h41_correct(1.,[f.Sample(1.,4),None],[0],False,False,.3,.2,.01,.3/.31)
        self.assertEqual(o.h41_ka,0.);self.assertEqual(o.drive_a,oldA);self.assertEqual(o.disturbance,.123)
        self.assertAlmostEqual(o.h41_pva,(1-.3/.31)*.1)
        self.assertAlmostEqual(o.h41_paa,.2)

    def test_clipped_effective_gain_full_Joseph(self):
        o=make();bound=m.drive_bound(o.c);o.drive_a=bound-.0001;o.disturbance=.13
        o.h41_pva=.1;o.h41_paa=.2;p=.3;r=.01;kv=p/(p+r);res=.2
        oldA=o.drive_a;d=o.disturbance
        o._h41_correct(1.,[f.Sample(1.,5),f.Sample(1.,5)],[0,1],True,False,p,res,r,kv)
        self.assertAlmostEqual(o.drive_a,bound)
        self.assertAlmostEqual(o.h41_ka,(bound-oldA)/res)
        expected=m.stabilize(*m.joseph(p,.1,.2,kv,o.h41_ka,r),o.c)
        self.assertEqual((o.pv,o.h41_pva,o.h41_paa),expected)
        self.assertEqual(d,o.disturbance)

    def test_bootstrap_STOPPED_reset(self):
        o=make()
        o.step(0.,f.Sample(0.,0.),f.Sample(0.,0.),f.Sample(0.,0.))
        self.assertEqual(o.h41_pva,0.);self.assertEqual(o.h41_paa,o.h41_sa)
        for i in range(1,50):
            t=i*.05;e=o.step(t,f.Sample(t,0.),f.Sample(t,0.),f.Sample(t,0.))
        self.assertEqual(e.mode,'STOPPED');self.assertEqual(e.v,0.);self.assertEqual(e.s,0.)
        self.assertEqual(o.h41_pva,0.);self.assertEqual(o.h41_paa,o.h41_sa)
        o.reset(position=7.);self.assertEqual(o.s,7.);self.assertEqual(o._distance_correction,0.)

    def test_actual_gain_and_precorrection_acceleration_readout(self):
        o=make();old_cor=0.
        checked=0
        for i in range(200):
            t=i*.05;ts=t-.02
            front=f.Sample(ts,5+.02*math.sin(t));rear=f.Sample(ts,5+.02*math.sin(t))
            old_cor=o._velocity_correction;e=o.step(t,f.Sample(ts,.5),front,rear)
            if i>20 and e.mode=='FUSED' and t>=o._blocked_until and abs(e.v)>1.:
                expected=(1.-o.h41_kv)*old_cor+o.h41_kv*o.readout.gain*o.h41_a_model*.02
                self.assertAlmostEqual(o._velocity_correction,expected,places=12);checked+=1
                self.assertGreaterEqual(o.h41_kv,0.);self.assertLessEqual(o.h41_kv,1.)
        self.assertGreater(checked,100)

    def test_published_distance_is_integral_no_recovery_reset(self):
        o=make();old=None;integral=0.;s0=None
        for i in range(600):
            t=i*.05;ts=(i//2)*.1;z=5+.03*math.sin(t)
            wheels=(None,None) if 150<=i<270 else (f.Sample(ts,z),f.Sample(ts,z))
            e=o.step(t,f.Sample(ts,.2),*wheels)
            if s0 is None:s0=e.s
            if old is not None:integral+=(old.v+e.v)*.5*(e.t-old.t)
            self.assertAlmostEqual(e.s-s0,integral,places=10);old=e

    def test_future_duplicate_prefix_nan_stale(self):
        a,b=make(),make()
        for i in range(120):
            t=i*.05;ts=(i//2)*.1
            args=(t,f.Sample(ts,.2),f.Sample(ts,4),f.Sample(ts,4))
            self.assertEqual(norm(a.step(*args)),norm(b.step(*args)))
        a.step(6.,f.Sample(7.,.8),f.Sample(8.,30),f.Sample(8.,30))
        b.step(6.,None,None,None)
        state_equal(self,b,a)
        e=a.step(6.05,f.Sample(6.05,float('nan')),None,None)
        self.assertTrue(e.command_stale);self.assertEqual(a.h41_ka,0.)
        with self.assertRaises(ValueError):a.step(6.05)
        with self.assertRaises(ValueError):a.step(4.)

    def test_low_speed_zero_lock_no_new_stop(self):
        o=make()
        for i in range(160):
            t=i*.05;z=1.5 if i<20 or i>100 else 0.
            e=o.step(t,f.Sample(t,0.),f.Sample(t,z),f.Sample(t,z))
            if 20<=i<100:self.assertNotEqual(e.mode,'STOPPED')
        self.assertGreater(e.v,1.)

    def test_common_quarantine_retained_and_no_actuator_learning(self):
        o=make()
        for i in range(60):
            t=i*.05;z=5. if i<20 or i>=44 else 10.
            e=o.step(t,f.Sample(t,.3),f.Sample(t,z),f.Sample(t,z))
            if 21<=i<44:
                self.assertNotEqual(e.mode,'REACQUIRING');self.assertEqual(o.h41_ka,0.)
        self.assertGreater(o.reacquire_blocked_until,1.)

    def test_base_hard_guard_methods_identical(self):
        import inspect
        for name in ('_wheel','_valid','_reacquire_pair','_take_pending_pair','_clear_reacquire','drive_target','resistance'):
            self.assertEqual(inspect.getsource(getattr(C,name)),inspect.getsource(getattr(f.GuardedReadoutObserver,name)))

    def test_role_gate_before_sql(self):
        store=f.Store(Path('/nonexistent'))
        with patch('sqlite3.connect',side_effect=AssertionError('SQL touched')):
            for role in ('test','validation'):
                bag=store.plan['splits'][role][0]
                with self.assertRaises(PermissionError):store.load(bag,role)

    def test_legacy_ObserverTests_on_enabled_candidate(self):
        sys.path.insert(0,str(f.ROOT/'tests'))
        import test_core
        old=test_core.Observer;test_core.Observer=C
        try:
            result=unittest.TestResult()
            unittest.defaultTestLoader.loadTestsFromTestCase(test_core.ObserverTests).run(result)
            self.assertTrue(result.wasSuccessful(),str(result.errors)+str(result.failures))
            print('NESTED_LEGACY_CASES',result.testsRun)
        finally:test_core.Observer=old

if __name__=='__main__':unittest.main()
