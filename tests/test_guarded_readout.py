"""Readout must improve delayed ramps without changing the inner baseline."""
from dataclasses import asdict
import json
import math
from pathlib import Path
import random
import unittest
from unittest.mock import patch
import test_core
from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.timeline import Timeline

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / 'src/reserve_odometry/config/guarded_readout_v7.json').read_text())


class GuardedProfileTests(test_core.ObserverTests):
    def setUp(self):
        def factory(config=None):
            return GuardedReadoutObserver(config or Config(**PROFILE['config']))
        self.patcher = patch.object(test_core, 'Observer', factory)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)


class GuardedReadoutTests(unittest.TestCase):
    def stream(self):
        rng = random.Random(781)
        held = [None, None]
        for i in range(601):
            t = i * .05
            u = .4 if t < 10 else -.15
            speed = max(.1, 3 + .15*t if t < 10 else 4.5 - .1*(t-10))
            if i % 2 == 0:
                ts = t - .025
                held = [Sample(ts, speed + rng.uniform(-.01, .01)) for _ in range(2)]
            f, r = held
            if 4 <= t < 6: f = Sample(t-.025, 12)
            if 10 <= t < 12: f = r = None
            if 16 <= t < 17: f = r = Sample(t-.025, 0)
            if 20 <= t < 21: f = Sample(t+1, 20)
            if 22 <= t < 23: r = Sample(t, float('nan'))
            command = None if 24 <= t < 25 else Sample(t, u)
            yield t, command, f, r

    def test_inner_state_exactly_main_through_faults(self):
        base = Observer(Config(**PROFILE['config']))
        guard = GuardedReadoutObserver(Config(**PROFILE['config']))
        changed = False
        for args in self.stream():
            a, b = base.step(*args), guard.step(*args)
            for key, value in vars(base).items():
                if key != 'last_estimate':
                    self.assertEqual(value, getattr(guard, key), key)
            self.assertEqual((a.mode,a.front_status,a.rear_status,a.command_stale),
                             (b.mode,b.front_status,b.rear_status,b.command_stale))
            self.assertGreaterEqual(b.variance_v, a.variance_v)
            self.assertGreaterEqual(b.variance_s, a.variance_s)
            self.assertIs(guard.last_estimate, b)
            changed |= a.v != b.v
        self.assertTrue(changed)

    def test_disabled_is_exactly_main(self):
        base = Observer(Config(**PROFILE['config']))
        guard = GuardedReadoutObserver(Config(**PROFILE['config']), readout=ReadoutConfig(gain=0))
        for args in self.stream():
            self.assertEqual(base.step(*args), guard.step(*args))

    def test_distance_and_acceleration_integrate_published_velocity(self):
        observer = GuardedReadoutObserver(Config(**PROFILE['config']))
        previous = None
        for args in self.stream():
            e = observer.step(*args)
            if previous is not None and e.mode != 'INITIALIZED':
                dt = e.t-previous.t
                self.assertAlmostEqual(e.s-previous.s, .5*(e.v+previous.v)*dt, places=11)
                self.assertAlmostEqual(e.a, (e.v-previous.v)/dt, places=10)
            previous = e

    def test_fault_resets_readout_and_holds_off(self):
        o = GuardedReadoutObserver(Config(**PROFILE['config']))
        for i in range(30):
            t=i*.05
            o.step(t,Sample(t,.5),Sample(t-.025,3+.1*t),Sample(t-.025,3+.1*t))
        self.assertNotEqual(o._velocity_correction, 0)
        e=o.step(1.5,Sample(1.5,.5),Sample(1.475,15),Sample(1.475,3.15))
        self.assertEqual(o._velocity_correction,0)
        self.assertEqual(e.v,o.v)
        for i in range(31,39):
            t=i*.05
            e=o.step(t,Sample(t,.5),Sample(t-.025,3+.1*t),Sample(t-.025,3+.1*t))
            self.assertEqual(o._velocity_correction,0)

    def test_delayed_constant_acceleration_bias_reduced(self):
        for accel in (.3,-.3):
            class Ramp(GuardedReadoutObserver):
                def drive_target(self,u,v): return accel
                def resistance(self,v): return 0.
            o=Ramp(Config(disturbance_limit_mps2=0.))
            o.reset(velocity=5);o.drive_a=accel
            raw_errors=[];corrected_errors=[]
            for i in range(201):
                t=i*.05; ts=t-.025
                e=o.step(t,Sample(t,.5),Sample(ts,5+accel*ts),Sample(ts,5+accel*ts))
                if t>1:
                    raw_errors.append((o.v-(5+accel*t))**2)
                    corrected_errors.append((e.v-(5+accel*t))**2)
            self.assertLess(sum(corrected_errors),1e-6*sum(raw_errors))

    def test_prediction_ticks_do_not_reassimilate_wheels(self):
        o=GuardedReadoutObserver(Config(**PROFILE['config'])); o.reset(velocity=3)
        o.step(0,Sample(0,.5),Sample(-.025,3),Sample(-.025,3))
        o.step(.05,Sample(.05,.5),Sample(.025,3.01),Sample(.025,3.01))
        correction=o._velocity_correction; used=list(o.used)
        o.step(.1,Sample(.1,.5),Sample(.025,3.01),Sample(.025,3.01))
        self.assertEqual(o.used,used)
        self.assertAlmostEqual(o._velocity_correction,correction,places=15)

    def test_bounds_reset_and_invalid_options(self):
        for kwargs in ({'gain':float('nan')},{'gain':-1},{'gain':1.01},
                       {'holdoff_s':float('inf')},{'holdoff_s':-1},{'holdoff_s':11}):
            with self.assertRaises(ValueError):ReadoutConfig(**kwargs)
        o=GuardedReadoutObserver(Config(**PROFILE['config']))
        for args in self.stream():
            e=o.step(*args)
            self.assertLessEqual(abs(e.v),o.c.max_speed_mps)
            self.assertLessEqual(abs(o._velocity_correction),o.c.max_accel_mps2*o.c.max_age_s)
            if o.v==0:self.assertEqual(e.v,0)
            else:self.assertGreaterEqual(e.v*o.v,0)
        o.reset(velocity=4,position=12)
        self.assertEqual((o._distance_correction,o._velocity_correction,o._correction_sigma_s),(0,0,0))
        self.assertEqual(o._blocked_until,-math.inf)
        self.assertIsNone(o.last_estimate)
        self.assertEqual((o.v,o.s),(4,12))

    def test_timeline_seek_resets_correction(self):
        tl=Timeline(GuardedReadoutObserver(Config(**PROFILE['config'])),delay_s=0)
        for i in range(31):
            t=i*.05
            for ch,v in ((0,.5),(1,3+.1*t),(2,3+.1*t)):tl.ingest(ch,Sample(t,v))
            list(tl.advance())
        list(tl.advance(now=0))
        self.assertEqual(tl.resets,1)
        self.assertEqual(tl.observer._distance_correction,0)
        self.assertIsNone(tl.observer.t)

    def test_future_values_do_not_change_prefix(self):
        def replay(future):
            tl=Timeline(GuardedReadoutObserver(Config(**PROFILE['config'])),delay_s=0)
            for ch,v in ((0,.5),(1,3),(2,3)):tl.ingest(ch,Sample(0,v))
            out=[e for e,_ in tl.advance(now=0)]
            tl.ingest(1,Sample(2,future))
            for i in range(1,16):out.extend(e for e,_ in tl.advance(now=i*.05))
            return out
        self.assertEqual(replay(4),replay(35))

    def test_profile_preserves_main_physics(self):
        main=json.loads((ROOT/'src/reserve_odometry/config/adaptive_v5.json').read_text())['config']
        self.assertEqual(PROFILE['config'],main)
        self.assertEqual(PROFILE['readout'],asdict(ReadoutConfig()))
        self.assertFalse(PROFILE['test_evaluated'])
        actual={}
        for line in (ROOT/'src/reserve_odometry/config/guarded_readout_v7.yaml').read_text().splitlines():
            key,sep,value=line.strip().partition(':')
            if sep and key.startswith(('model.','readout.')):actual[key]=float(value)
        expected={'model.'+k:v for k,v in main.items()}
        expected.update({'readout.'+k:v for k,v in PROFILE['readout'].items()})
        self.assertEqual(actual,expected)
