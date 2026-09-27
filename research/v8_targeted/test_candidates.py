"""Implementation and causality tests. Synthetic signals are not accuracy evidence."""
from dataclasses import asdict
import importlib.util
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import candidates as c
from reserve_odometry.core import Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver
spec=importlib.util.spec_from_file_location('targeted_test_eval',HERE/'evaluate.py')
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)


def inputs(n=1600):
    f=r=None
    for i in range(n):
        t=i*.05;phase=t%30;u=.35 if phase<10 else (-.25 if phase<22 else 0.)
        v=4+.3*math.sin(t/3)
        if i%2==0:f=Sample(t-.025,v);r=Sample(t-.02,v+.005)
        ff,rr=f,r
        if 10<=phase<13:ff=rr=None
        if 14<=phase<15:ff=Sample(t,15.)
        if 17<=phase<18:ff=rr=Sample(t,0.)
        if 23<=phase<24:rr=Sample(t+1,34.)
        command=None if 26<=phase<27 else Sample(t,u)
        yield t,command,ff,rr


class ConfigTests(unittest.TestCase):
    def test_source_pins(self):self.assertEqual(len(e.pins()),19)
    def test_canonical_fields(self):
        cfg,readout=c.configuration('main');d=json.loads((c.ROOT/'src/reserve_odometry/config/champion_v8.json').read_text())
        self.assertEqual(asdict(cfg),d['config']);self.assertEqual(asdict(readout),d['readout'])
    def test_unknown_variant(self):
        with self.assertRaises(ValueError):c.configuration('winner_unknown')
    def test_one_or_two_declared_fields_only(self):
        base,ro=c.configuration('main')
        for name,multipliers in c.VARIANTS.items():
            with self.subTest(name=name):
                cfg,r=c.configuration(name)
                self.assertEqual(ro,r)
                changed={k for k in asdict(cfg) if getattr(cfg,k)!=getattr(base,k)}
                self.assertEqual(changed,set(multipliers))
    def test_caps(self):
        for name,cap in [('disturbance_080',.8),('disturbance_100',1.),('disturbance_120',1.2)]:
            self.assertEqual(c.configuration(name)[0].disturbance_limit_mps2,cap)
    def test_not_shared(self):
        a,_=c.configuration('main');a.mass_kg=1
        self.assertEqual(c.configuration('main')[0].mass_kg,40000.)
    def test_preserve_braking_in_cap_variants(self):
        for name in ('disturbance_080','disturbance_100','disturbance_120'):
            cfg,_=c.configuration(name);base,_=c.configuration('main')
            a,b=GuardedReadoutObserver(cfg),GuardedReadoutObserver(base)
            for v in (-15.,-2.,0.,2.,15.):
                for u in (-1.,-.4,0.,.4,1.):self.assertEqual(a.drive_target(u,v),b.drive_target(u,v))


class RuntimeTests(unittest.TestCase):
    def test_static_model_equals_independent_config(self):
        base,ro=c.configuration('main')
        for name in c.VARIANTS:
            if name=='carry_readout':continue
            config_dict=asdict(base)
            for key,m in c.VARIANTS[name].items():config_dict[key]*=m
            independent=GuardedReadoutObserver(c.Config(**config_dict),readout=ro)
            factory,cfg=c.models([name])[name];actual=factory(cfg)
            for args in inputs(400):self.assertEqual(actual.step(*args),independent.step(*args))
    def test_all_variants_integral_and_bounds(self):
        for name,(factory,config) in c.models().items():
            with self.subTest(name=name):
                o=factory(config);prev=None
                for args in inputs():
                    x=o.step(*args)
                    self.assertTrue(all(math.isfinite(z) for z in (x.v,x.s,x.a,x.variance_v,x.disturbance)))
                    self.assertLessEqual(abs(x.v),config.max_speed_mps)
                    self.assertLessEqual(abs(o.disturbance),config.disturbance_limit_mps2)
                    if prev is not None:self.assertAlmostEqual(x.s-prev.s,.5*(prev.v+x.v)*(x.t-prev.t),places=9)
                    prev=x
    def test_future_values_cannot_influence_prefix(self):
        for name,(factory,config) in c.models().items():
            a,b=factory(config),factory(config)
            for args in inputs(60):a.step(*args);b.step(*args)
            for i in range(60,90):
                t=i*.05
                self.assertEqual(a.step(t,Sample(t,.3),Sample(t+1,2.),Sample(t+1,2.)),b.step(t,Sample(t,.3),Sample(t+1,39.),Sample(t+1,-39.)))
    def test_reset_equivalence(self):
        for name,(factory,config) in c.models().items():
            a,b=factory(config),factory(config)
            for args in inputs(100):a.step(*args)
            a.reset(velocity=2.,position=10.);b.reset(velocity=2.,position=10.)
            self.assertEqual(vars(a),vars(b))
    def test_cap_saturation_both_signs(self):
        for name in ('main','disturbance_080','disturbance_100','disturbance_120'):
            factory,config=c.models([name])[name]
            for sign in [-1.,1.]:
                o=factory(config)
                for i in range(200):
                    t=i*.05;v=10+sign*.3*t;u=-sign
                    o.step(t,Sample(t,u),Sample(t,v),Sample(t,v))
                self.assertLessEqual(abs(o.disturbance),config.disturbance_limit_mps2)
    def test_larger_cap_really_used_on_mismatch_fixture(self):
        maxima=[]
        for name in ('main','disturbance_100'):
            factory,config=c.models([name])[name];o=factory(config)
            for i in range(300):
                t=i*.05;v=3+.12*t
                o.step(t,Sample(t,-.5333),Sample(t,v),Sample(t,v))
            maxima.append(o.disturbance)
        self.assertEqual(maxima[0],.6);self.assertGreater(maxima[1],.8)
    def test_carry_off_is_exact(self):
        config,readout=c.configuration('main');a=GuardedReadoutObserver(config,readout=readout)
        b=c.CarryReadout(config,readout=readout,enabled=False)
        for args in inputs(3000):self.assertEqual(a.step(*args),b.step(*args))
    def test_carry_inner_is_unchanged(self):
        config,readout=c.configuration('main');a=GuardedReadoutObserver(config,readout=readout);b=c.CarryReadout(config,readout=readout)
        for args in inputs(2000):
            a.step(*args);b.step(*args)
            for key,value in vars(a).items():
                if key!='last_estimate':self.assertEqual(value,getattr(b,key))
    def test_clock_reversal_denied(self):
        for _,(factory,config) in c.models().items():
            o=factory(config);o.step(1.)
            with self.assertRaises(ValueError):o.step(.9)
    def test_state_dimension_bounded(self):
        for name,(factory,config) in c.models().items():
            o=factory(config);keys=set(vars(o))
            for args in inputs(1000):o.step(*args)
            self.assertEqual(keys,set(vars(o)))
            for value in vars(o).values():
                if isinstance(value,(list,tuple,dict)):self.assertLessEqual(len(value),8)


class RunnerTests(unittest.TestCase):
    def test_non_development_before_io(self):
        store=e.DevelopmentStore('/not-present')
        with patch.object(e.ev,'sha',side_effect=AssertionError('Unexpected file IO')):
            for role in ('train','validation','test'):
                with self.assertRaises(PermissionError):store.load(store.plan['splits'][role][0])
    def test_purpose_cannot_bypass_role(self):
        store=e.DevelopmentStore('/not-present');bag=store.plan['splits']['development'][0]
        with patch.object(e.sqlite3,'connect',side_effect=AssertionError('Unexpected SQL')):
            with self.assertRaises(PermissionError):store.load(bag,'validation')
    def test_existing_output_refused(self):
        with self.assertRaises(FileExistsError):e.run('/not-present',HERE,['main'],False,1)
    def test_frozen_function_unchanged(self):
        self.assertEqual(e.ev.sha(c.ROOT/'tools/research_guarded/compare.py'),e.pins()['tools/research_guarded/compare.py'])


if __name__=='__main__':unittest.main()
