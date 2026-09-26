"""Synthetic mechanism tests. Never a substitute for paired real-data accuracy."""
import ast
from dataclasses import FrozenInstanceError
import math
from pathlib import Path
import random
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from factory import baseline, load_profile, prototype
from runtime import ResidualScale, ResidualScaleObserver
from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.timeline import Timeline


def stream(n=2000):
    rng = random.Random(4505)
    held = [None, None]
    for i in range(n):
        t = i * .05
        if i % 2 == 0:
            speed = 3.0 + .4 * math.sin(t * .2)
            held = [Sample(t-.025, speed+rng.uniform(-.005,.005)) for _ in range(2)]
        f, r = held
        phase = i % 400
        if 80 <= phase < 110: f = r = None
        if 150 <= phase < 165: f = Sample(t-.025, 9)
        if 190 <= phase < 200: f = r = Sample(t-.025, 0.)
        if 230 <= phase < 235: f = Sample(t+1, 5)
        if 280 <= phase < 285: r = Sample(t, float('nan'))
        if 330 <= phase < 340: r = Sample(t, 40.1)
        command = None if 350 <= phase < 365 else Sample(t, .4 if phase < 180 else -.1)
        yield t, command, f, r


class RuntimeTests(unittest.TestCase):
    def active(self, f=1.02, r=1.02):
        return prototype(ResidualScale(f, r, True))

    def assert_legacy_state(self, expected, actual):
        for k,v in vars(expected).items():
            self.assertEqual(v, getattr(actual, k), k)

    def test_config_rejects_invalid_factors(self):
        for value in (0, .969999, 1.030001, math.inf, math.nan, True, '1'):
            for name in ('front','rear'):
                with self.subTest(value=value,name=name), self.assertRaises(ValueError):
                    ResidualScale(**{name:value})
        with self.assertRaises(ValueError): ResidualScale(enabled=1)

    def test_boundary_values_and_immutable_parameters(self):
        c=ResidualScale(.97,1.03,True)
        self.assertTrue(c.active)
        with self.assertRaises(FrozenInstanceError): c.front=1.01
        o=prototype(c)
        with self.assertRaises(AttributeError): o.calibration=ResidualScale()

    def test_complete_profile_not_config_defaults(self):
        c,r,ops=load_profile()
        self.assertEqual(c.adaptation_tau_s,.5)
        self.assertEqual(c.common_mode_quarantine_s,1.5)
        self.assertEqual(c.wheel_time_compensation,0)
        self.assertEqual(r,ReadoutConfig(1,.5))
        self.assertEqual((ops['rate_hz'],ops['alignment_delay_s']),(20,0))
        self.assertNotEqual(c,Config())

    def test_explicit_types_required(self):
        with self.assertRaises(TypeError): ResidualScaleObserver(None,calibration=ResidualScale(),readout=ReadoutConfig())
        c,r,_=load_profile()
        with self.assertRaises(TypeError): ResidualScaleObserver(c,calibration=None,readout=r)

    def test_disabled_exact_all_inherited_fields_6000_steps(self):
        a,b=baseline(),prototype(ResidualScale(.97,1.03,False))
        for args in stream(6000):
            self.assertEqual(a.step(*args),b.step(*args))
            self.assert_legacy_state(a,b)

    def test_enabled_identity_exact_all_fields_6000_steps(self):
        a,b=baseline(),prototype(ResidualScale(1,1,True))
        for args in stream(6000):
            self.assertEqual(a.step(*args),b.step(*args))
            self.assert_legacy_state(a,b)

    def test_unit_conversion_is_not_applied_twice(self):
        o=self.active()
        e=o.step(0,Sample(0,0),Sample(0,36/3.6),Sample(0,36/3.6))
        self.assertEqual(e.v,10*1.02)

    def test_scale_preserves_stamp_zero_and_sign(self):
        o=self.active()
        for v in (-30.,-1.,0.,1.,30.):
            x=Sample(12.345,v); y=o._scale(x,1.02)
            self.assertEqual(y.t,x.t)
            self.assertEqual(y.value,1.02*v)
            self.assertGreaterEqual(y.value*x.value,0)
        self.assertEqual(o._scale(Sample(1,0),.97).value,0.)

    def test_active_clean_matches_independent_calibrated_input_observer(self):
        a,b=baseline(),self.active(1.02,.99)
        for i in range(1000):
            t=i*.05; v=4+.1*math.sin(.1*t); stamp=t-.025
            u=Sample(t,.15)
            f,r=Sample(stamp,v),Sample(stamp,v+.01)
            expected=a.step(t,u,Sample(stamp,f.value*1.02),Sample(stamp,r.value*.99))
            actual=b.step(t,u,f,r)
            self.assertEqual(expected,actual)
            self.assert_legacy_state(a,b)

    def test_raw_range_cannot_be_rescued_by_downscale(self):
        o=self.active(.97,.97)
        e=o.step(0,Sample(0,0),Sample(0,40.1),Sample(0,40.1))
        self.assertEqual((e.front_status,e.rear_status),('RANGE','RANGE'))
        self.assertEqual(e.mode,'WAITING_FOR_INITIALIZATION')

    def test_corrected_range_rejected_even_on_repeated_raw_sample(self):
        o=self.active(1.03,1.03)
        for t in (0,.05,.10):
            e=o.step(t,Sample(t,0),Sample(0,39.5),Sample(0,39.5))
            self.assertEqual((e.front_status,e.rear_status),('RANGE','RANGE'))

    def test_raw_rate_cannot_be_rescued_and_quarantine_preserved(self):
        o=self.active(.97,.97)
        o.step(0,Sample(0,0),Sample(0,3),Sample(0,3))
        e=o.step(.1,Sample(.1,0),Sample(.1,3.66),Sample(.1,3.66))
        self.assertEqual((e.front_status,e.rear_status),('RATE_ANOMALY','RATE_ANOMALY'))
        self.assertEqual(o.reacquire_blocked_until,1.6)
        self.assertEqual(o._raw_gate.used,[.1,.1])

    def test_corrected_rate_is_additional_veto(self):
        o=self.active(1.03,1.03)
        o.step(0,Sample(0,0),Sample(0,3),Sample(0,3))
        e=o.step(.1,Sample(.1,0),Sample(.1,3.64),Sample(.1,3.64))
        self.assertEqual((e.front_status,e.rear_status),('RATE_ANOMALY','RATE_ANOMALY'))
        self.assertEqual(o._raw_gate.rate_anomaly_times,[None,None])

    def test_future_wheel_values_ignored(self):
        a,b=self.active(),self.active()
        for o in (a,b): o.step(0,Sample(0,.1),Sample(0,3),Sample(0,3))
        ea=a.step(.05,Sample(.05,.1),Sample(2,4),Sample(2,4))
        eb=b.step(.05,Sample(.05,.1),Sample(2,38),Sample(2,38))
        self.assertEqual(ea,eb)
        self.assertEqual(a._raw_gate.used,[0,0])

    def test_stale_wheels_not_consumed(self):
        o=self.active()
        o.step(0,Sample(0,0),Sample(0,3),Sample(0,3))
        e=o.step(.1,Sample(.1,0),Sample(-1,2),Sample(-1,2))
        self.assertEqual(e.front_status,'MISSING_OR_STALE')
        self.assertEqual(o._raw_gate.used,[0,0])

    def test_invalid_float_samples_preserve_finite_outputs(self):
        o=self.active(); o.reset(velocity=3)
        for i,value in enumerate((float('nan'),float('inf'),-float('inf'),1e308)):
            t=i*.05
            e=o.step(t,Sample(t,0),Sample(t,value),Sample(t,value))
            self.assertTrue(all(math.isfinite(x) for x in (e.v,e.s,e.a,e.disturbance)))
            self.assertIsNone(o._raw_inputs)

    def test_duplicate_samples_never_reassimilated(self):
        o=self.active()
        f=r=Sample(0,3)
        o.step(0,Sample(0,.2),f,r)
        for t in (.05,.1,.15,.2):
            e=o.step(t,Sample(t,.2),f,r)
            self.assertEqual(e.front_status,'DUPLICATE_OR_OLD')
            self.assertEqual(o.used,[0,0]); self.assertEqual(o._raw_gate.used,[0,0])

    def test_stale_command_keeps_disturbance_frozen(self):
        o=self.active()
        o.reset(velocity=3); o.disturbance=.123
        for i in range(10):
            t=i*.05
            e=o.step(t,None,Sample(t,3),Sample(t,3))
            self.assertTrue(e.command_stale)
            self.assertEqual(o.disturbance,.123)

    def test_true_zero_stop_remains_zero(self):
        o=self.active(.97,1.03)
        for i in range(30):
            t=i*.05; e=o.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
            self.assertEqual(e.v,0); self.assertEqual(e.s,0)
        self.assertEqual(e.mode,'STOPPED')

    def test_low_speed_common_zero_lock_not_stop(self):
        o=self.active()
        o.step(0,Sample(0,0),Sample(0,1.5),Sample(0,1.5))
        for i in range(1,21):
            t=i*.05; e=o.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
            self.assertNotEqual(e.mode,'STOPPED')
            self.assertGreater(e.v,.25)

    def test_reverse_bootstrap_sign(self):
        o=self.active()
        e=o.step(0,Sample(0,0),Sample(0,-3),Sample(0,-3))
        self.assertEqual(e.v,-3*1.02)

    def test_realistic_post_dropout_not_spurious_rate_quarantine(self):
        o=self.active()
        o.step(0,Sample(0,0),Sample(0,3),Sample(0,3))
        for i in range(1,41):
            t=i*.05; o.step(t,Sample(t,0),None,None)
        o.step(2.05,Sample(2.05,0),Sample(2.05,5),Sample(2.05,5))
        self.assertEqual(o._raw_gate.rate_anomaly_times,[None,None])
        self.assertEqual(o.reacquire_blocked_until,-math.inf)

    def test_distance_and_derivative_consistent_through_faults(self):
        o=self.active(); old=None
        for args in stream(2000):
            e=o.step(*args)
            if old is not None and e.mode!='INITIALIZED':
                dt=e.t-old.t
                self.assertAlmostEqual(e.s-old.s,.5*(old.v+e.v)*dt,places=10)
                self.assertAlmostEqual(e.a,(e.v-old.v)/dt,places=9)
            old=e

    def test_distance_difference_not_erased_at_recovery(self):
        a,b=baseline(),self.active(); previous=None; accumulated=0.
        for i in range(501):
            t=i*.05
            f=r=None if 5<t<7 else Sample(t-.02,3.)
            ea=a.step(t,Sample(t,0),f,r); eb=b.step(t,Sample(t,0),f,r)
            difference=eb.v-ea.v
            if previous is not None:
                accumulated+=.5*(difference+previous)*.05
                self.assertAlmostEqual(eb.s-ea.s,accumulated,places=9)
            previous=difference
        self.assertGreater(abs(eb.s-ea.s),.1)

    def test_reset_clears_raw_guard_and_new_segment(self):
        o=self.active()
        for args in stream(50):o.step(*args)
        o.reset(velocity=-2,position=8)
        self.assertEqual(o._raw_gate.used,[None,None])
        self.assertEqual(o._raw_gate.raw_previous,[None,None])
        self.assertEqual(o._raw_gate.reacquire_blocked_until,-math.inf)
        self.assertIsNone(o._raw_inputs); self.assertIsNone(o.t)
        self.assertEqual((o.s,o.v),(8,-2))

    def test_invalid_time_no_raw_guard_mutation(self):
        o=self.active(); o.step(0,Sample(0,0),Sample(0,3),Sample(0,3))
        for t in (0,-1,float('nan'),1):
            with self.assertRaises(ValueError):o.step(t,Sample(t,0),Sample(t,3),Sample(t,3))
            self.assertEqual(o._raw_gate.used,[0,0]); self.assertIsNone(o._raw_inputs)

    def test_constant_memory_structure_10000_steps(self):
        o=self.active(); keys=set(vars(o)); raw_id=id(o._raw_gate)
        for args in stream(10000):
            e=o.step(*args)
            self.assertEqual(set(vars(o)),keys)
            self.assertEqual(id(o._raw_gate),raw_id)
            self.assertIsNone(o._raw_inputs)
            for name in ('used','raw_previous','rate_anomaly_times'):
                self.assertEqual(len(getattr(o._raw_gate,name)),2)
            self.assertLessEqual(abs(e.v),o.c.max_speed_mps)
            self.assertLessEqual(abs(e.disturbance),o.c.disturbance_limit_mps2)

    def test_timeline_prefix_unaffected_by_future_value(self):
        def run(future):
            tl=Timeline(self.active(),rate_hz=20,delay_s=0)
            for ch,v in ((0,.1),(1,3),(2,3)):tl.ingest(ch,Sample(0,v))
            out=[e for e,_ in tl.advance(now=0)]
            tl.ingest(1,Sample(2,future))
            for i in range(1,20):
                for e,held in tl.advance(now=i*.05):
                    self.assertTrue(all(x is None or x.t<=e.t+1e-9 for x in held))
                    out.append(e)
            return out
        self.assertEqual(run(3),run(35))

    def test_timeline_disabled_outputs_and_counters_exact(self):
        tls=[Timeline(o,rate_hz=20,delay_s=0) for o in (baseline(),prototype(ResidualScale(.97,1.03,False)))]
        for i in range(300):
            t=i*.05
            for ch,v in ((0,.1),(1,3+.1*math.sin(t)),(2,3)):
                accepted=[tl.ingest(ch,Sample(t,v)) for tl in tls]
                self.assertEqual(accepted[0],accepted[1])
            out=[list(tl.advance()) for tl in tls]; self.assertEqual(out[0],out[1])
        for k in ('dropped','resets','catchup_events','tick_index','next_tick'):
            self.assertEqual(getattr(tls[0],k),getattr(tls[1],k))

    def test_timeline_seek_opens_clean_segment(self):
        tl=Timeline(self.active(),rate_hz=20,delay_s=0)
        for i in range(31):
            t=i*.05
            for ch,v in ((0,0),(1,3),(2,3)):tl.ingest(ch,Sample(t,v))
            list(tl.advance())
        list(tl.advance(now=0))
        self.assertEqual(tl.resets,1);self.assertEqual(tl.observer._raw_gate.used,[None,None])
        self.assertEqual(tl.observer.s,0)

    def test_no_scientific_or_external_runtime_imports(self):
        tree=ast.parse((HERE/'runtime.py').read_text())
        allowed={'dataclasses','math','typing','reserve_odometry.core','reserve_odometry.guarded_readout'}
        imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import): imports.extend(a.name for a in node.names)
            if isinstance(node,ast.ImportFrom): imports.append(node.module)
        self.assertLessEqual(set(imports),allowed)

    def test_original_motion_and_recovery_methods_reused(self):
        o=self.active()
        for name in ('drive_target','resistance','_reacquire_pair','_take_pending_pair','_clear_reacquire'):
            self.assertIs(getattr(o,name).__func__,getattr(Observer,name))


if __name__=='__main__':unittest.main()
