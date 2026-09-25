"""Mechanism tests; these do NOT assert real-data accuracy."""
import dataclasses
import importlib.util
import json
import math
from pathlib import Path
import random
import sys
import unittest

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(ROOT/'src/reserve_odometry')]
from _canonical.guarded_readout import GuardedReadoutObserver as Canonical
from reserve_odometry.core import Config,Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver,ReadoutConfig
from reserve_odometry.drive_disturbance import DriveDependentObserver,DriveCorrectionConfig

PROFILE=json.loads((ROOT/'src/reserve_odometry/config/guarded_readout_v7.json').read_text())
def cfg():return Config(**PROFILE['config'])
def norm(x):
    if dataclasses.is_dataclass(x):return dataclasses.asdict(x)
    if isinstance(x,(list,tuple)):return [norm(y) for y in x]
    if isinstance(x,dict):return {k:norm(v) for k,v in x.items()}
    return x

def fit_data(o,t=2.,constant=False,slope=.2,n=20):
    o.history.clear()
    for i in range(n):
        x=.1 if constant else -0.4+.04*i
        o.history.append((t-(n-1-i)*.08,x,.03+slope*x))
    o._fit(t)

class H15Tests(unittest.TestCase):
    def test_invalid_options(self):
        for v in (float('nan'),float('inf'),0,-1,.02):
            with self.assertRaises(ValueError):DriveCorrectionConfig(ridge=v)
        with self.assertRaises(ValueError):DriveCorrectionConfig(enabled=1)

    def test_exact_disabled_canonical_all_original_fields(self):
        ref=Canonical(cfg());off=DriveDependentObserver(cfg(),correction=DriveCorrectionConfig(enabled=False))
        rng=random.Random(1502)
        for i in range(6000):
            t=i*.05; ts=(i//2)*.1
            u=.3*math.sin(t*.3);z=5+.2*math.sin(ts*.4)
            f=r=Sample(ts,z)
            if 15<t%40<19:f=r=None
            if 23<t%40<24:f=Sample(ts,z+5)
            if 30<t%40<31:f=r=Sample(ts,0)
            if i%711==0:f=Sample(t+.2,z)
            cmd=Sample(ts,u) if i%533 else None
            a=ref.step(t,cmd,f,r);b=off.step(t,cmd,f,r)
            self.assertEqual(norm(a),norm(b))
            for k,v in vars(ref).items():self.assertEqual(norm(v),norm(getattr(off,k)),(i,k))
        self.assertEqual(off.stats['effective_ticks'],0)

    def test_healthy_estimates_unchanged(self):
        ref=Canonical(cfg());o=DriveDependentObserver(cfg())
        for i in range(1500):
            t=i*.05;ts=(i//2)*.1
            u=.25*math.sin(t*.3);z=5+.4*math.sin(ts*.35)
            args=(t,Sample(ts,u),Sample(ts,z),Sample(ts,z))
            self.assertEqual(norm(ref.step(*args)),norm(o.step(*args)))
            self.assertEqual(ref.disturbance,o.disturbance)
        self.assertGreater(o.stats['trusted_points'],0)

    def test_ridge_closed_form(self):
        for lam in (.01,.04):
            o=DriveDependentObserver(cfg(),correction=DriveCorrectionConfig(ridge=lam));fit_data(o)
            vx=o.drive_variance
            self.assertTrue(o.fit_ok)
            self.assertAlmostEqual(o.gamma,.2*vx/(vx+lam),places=14)

    def test_no_identification_constant_drive(self):
        o=DriveDependentObserver(cfg());fit_data(o,constant=True)
        self.assertFalse(o.fit_ok);self.assertEqual(o.gamma,0)

    def test_insufficient_span(self):
        o=DriveDependentObserver(cfg());fit_data(o,n=6)
        self.assertFalse(o.fit_ok)

    def test_old_history_fallback(self):
        o=DriveDependentObserver(cfg());fit_data(o);o._fit(2.6)
        self.assertFalse(o.fit_ok)

    def test_small_excitation_fallback(self):
        o=DriveDependentObserver(cfg());fit_data(o)
        o.history=type(o.history)(((t,x*.01,y) for t,x,y in o.history),maxlen=40)
        o._fit(2.);self.assertFalse(o.fit_ok)

    def test_gamma_bounded_under_correlated_slip(self):
        o=DriveDependentObserver(cfg());fit_data(o,slope=1.)
        # Common-mode acceleration contamination can masquerade as gamma.
        self.assertTrue(o.fit_ok);self.assertEqual(o.gamma,.25)
        self.assertEqual(o.stats['gamma_saturated'],1)

    def test_bad_fit_fallback(self):
        o=DriveDependentObserver(cfg());fit_data(o)
        o.history=type(o.history)(((t,x,2.*(-1)**i) for i,(t,x,y) in enumerate(o.history)),maxlen=40)
        o._fit(2.);self.assertFalse(o.fit_ok)

    def test_loss_onset_continuity_and_frozen_gamma(self):
        o=DriveDependentObserver(cfg());o.disturbance=.2;o.drive_a=.4;fit_data(o)
        d=o._h15_prediction(2.,False,[],['MISSING_OR_STALE']*2)
        self.assertEqual(d,.2);loss=o.loss
        self.assertNotEqual(loss[2],0);self.assertEqual(len(o.history),0)
        o.drive_a=-.4;effective=o._h15_prediction(2.1,False,[],['MISSING_OR_STALE']*2)
        self.assertAlmostEqual(effective,.2+loss[2]*(-.8))
        self.assertEqual(o.loss,loss)
        o._h15_observe(2.1,2.1,5.,.1,[Sample(2.1,5)]*2,5.)
        self.assertEqual(len(o.history),0)

    def test_duplicate_tick_not_loss(self):
        o=DriveDependentObserver(cfg());fit_data(o)
        o._h15_prediction(2.,False,[],['DUPLICATE_OR_OLD']*2)
        self.assertIsNone(o.loss);self.assertEqual(len(o.history),20)

    def test_effective_clipped(self):
        o=DriveDependentObserver(cfg());o.loss=(.59,0.,.25);o.drive_a=10.
        self.assertEqual(o._h15_prediction(1.,False,[],['MISSING_OR_STALE']*2),.6)

    def test_stale_cancels_loss_session_permanently(self):
        o=DriveDependentObserver(cfg());o.disturbance=.2;o.loss=(.2,.3,.25);o.drive_a=0
        self.assertEqual(o._h15_prediction(1.,True,[],['MISSING_OR_STALE']*2),.2)
        self.assertEqual(o._h15_prediction(1.1,False,[],['MISSING_OR_STALE']*2),.2)
        self.assertEqual(o.loss[2],0)

    def test_recovery_returns_legacy(self):
        o=DriveDependentObserver(cfg());o.disturbance=.2;o.loss=(.2,.3,.25);o.drive_a=0
        self.assertEqual(o._h15_prediction(1.,False,[0,1],['ACCEPTED']*2),.2)
        self.assertIsNone(o.loss)

    def test_history_count_and_time_bounded(self):
        o=DriveDependentObserver(cfg())
        for i in range(10000):
            t=i*.05;o.drive_a=.3*math.sin(t)
            o._h15_observe(t,t,5.,.1,[Sample(t,5.)]*2,5.)
            self.assertLessEqual(len(o.history),40)
            self.assertLessEqual(t-o.history[0][0],2.)
        o._h15_prediction(1000.,False,[],['DUPLICATE_OR_OLD']*2)
        self.assertEqual(len(o.history),0)

    def test_reset_clears_auxiliary_state(self):
        o=DriveDependentObserver(cfg());fit_data(o);o.loss=(.2,.3,.25)
        o.reset(velocity=4.)
        self.assertEqual(len(o.history),0);self.assertIsNone(o.loss)
        self.assertEqual(o.stats['fits'],0);self.assertEqual(o.gamma,0)

    def test_future_nan_and_duplicates_do_not_train(self):
        o=DriveDependentObserver(cfg());o.reset(velocity=5)
        for i in range(100):
            t=i*.05
            o.step(t,Sample(t,.2),Sample(t+.1,5),Sample(t,float('nan')))
        self.assertEqual(o.stats['trusted_points'],0)
        o.reset(velocity=5)
        for i in range(5):o.step(i*.05,Sample(0,.2),Sample(0,5),Sample(0,5))
        self.assertEqual(o.stats['trusted_points'],0)

    def test_prefix_causality(self):
        def replay(count,alter_after=None):
            o=DriveDependentObserver(cfg());result=[]
            for i in range(count):
                t=i*.05;ts=(i//2)*.1
                z=5+.1*math.sin(ts)
                if alter_after is not None and i>=alter_after:z=12
                result.append(norm(o.step(t,Sample(ts,.2),Sample(ts,z),Sample(ts,z))))
            return result
        self.assertEqual(replay(250),replay(500,250)[:250])

    def test_zero_lock_guard_retained(self):
        o=DriveDependentObserver(cfg());o.reset(velocity=1.5)
        for i in range(40):
            t=i*.05;e=o.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
            self.assertNotEqual(e.mode,'STOPPED')
            self.assertNotEqual(e.front_status,'ACCEPTED')

    def test_actual_hook_changes_prediction_but_not_legacy_d(self):
        a=Canonical(cfg());b=DriveDependentObserver(cfg())
        a.reset(velocity=5.);b.reset(velocity=5.)
        for o in (a,b):o.t=2.;o.drive_a=.4;o.disturbance=.2
        fit_data(b)
        args=(2.05,Sample(2.05,-.2),None,None)
        self.assertEqual(norm(a.step(*args)),norm(b.step(*args)))
        self.assertNotEqual(b.loss[2],0.)
        aa=a.step(2.1,Sample(2.1,-.2),None,None)
        bb=b.step(2.1,Sample(2.1,-.2),None,None)
        self.assertNotEqual(aa.v,bb.v);self.assertEqual(a.disturbance,b.disturbance)
        self.assertGreater(b.stats['effective_ticks'],0)

    def test_source_runtime_dependencies(self):
        import ast
        p=ROOT/'src/reserve_odometry/reserve_odometry/drive_disturbance.py'
        tree=ast.parse(p.read_text())
        imports=[n.names[0].name for n in ast.walk(tree) if isinstance(n,ast.Import)]
        self.assertEqual(imports,['math'])

if __name__=='__main__':unittest.main()
