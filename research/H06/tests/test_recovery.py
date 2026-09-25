"""Mechanism/invariant probes only; not evidence of real-recording accuracy."""
from dataclasses import asdict
import importlib.util
import math
from pathlib import Path
import random
import subprocess
import sys
import unittest

from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.recovery import RecoveryConfig, RecoveryObserver

ROOT = Path(__file__).resolve().parents[3]
BASE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
CORE = 'src/reserve_odometry/reserve_odometry/core.py'


def original_observer():
    local = ROOT / 'core_baseline.py'
    if local.exists():
        source = local.read_bytes()
    else:
        source = subprocess.check_output(['git', 'show', BASE + ':' + CORE], cwd=ROOT)
    import hashlib
    digest = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
    if digest != 'f6fc8ecd0b4e16018d814407b1944ce26ea550b0':
        raise AssertionError('Wrong baseline core')
    spec = importlib.util.spec_from_loader('h06_original_core', loader=None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(source, BASE + ':' + CORE, 'exec'), module.__dict__)
    return module.Observer


def policy_observer():
    o = RecoveryObserver(Config(adaptation_tau_s=.5))
    o.reset(velocity=5.)
    o._recovery_previous_v = 5.
    o._recovery_command_valid = True
    o.drive_a = .5 + o.resistance(5.)
    return o


def feed_policy(o, t, z, gap=0.):
    return o._reacquire_pair((Sample(t, z), Sample(t, z + gap)), 5.)


class RecoveryTests(unittest.TestCase):
    def test_config_has_identical_physics(self):
        self.assertEqual(asdict(Config()), asdict(RecoveryConfig()))

    def test_default_hooks_are_bitwise_baseline(self):
        old = original_observer()(Config(adaptation_tau_s=.5))
        new = Observer(Config(adaptation_tau_s=.5))
        rng = random.Random(6006)
        held = [None, None, None]
        for i in range(10000):
            t = i * .05
            if i % 2 == 0:
                v = 5 + .5 * math.sin(t / 4)
                u = .4 * math.sin(t / 3)
                front, rear = v, v
                phase = i % 200
                if 40 <= phase < 80:
                    front += 5
                if 100 <= phase < 140:
                    front = rear = 0
                held = [Sample(t, u), Sample(t, front), Sample(t, rear)]
                if 150 <= phase < 180:
                    held[1:] = [None, None]
                if rng.random() < .01:
                    held[1] = Sample(t + .5, float('nan'))
            self.assertEqual(asdict(old.step(t, *held)), asdict(new.step(t, *held)))

    def test_dynamic_evidence_shortens_dwell(self):
        o = policy_observer()
        for k in range(4):
            self.assertIsNone(feed_policy(o, k * .1, 10 + .05 * k))
        self.assertIsNotNone(feed_policy(o, .4, 10.2))
        self.assertAlmostEqual(o.recovery_evidence_s, .4)

    def test_constant_false_pair_keeps_original_dwell(self):
        o = policy_observer()
        for k in range(8):
            self.assertIsNone(feed_policy(o, k * .1, 10.))
        self.assertEqual(o.recovery_evidence_s, 0.)
        self.assertEqual(feed_policy(o, .8, 10.), 10.)

    def test_bad_dynamic_evidence_decays_twice_as_fast(self):
        o = policy_observer()
        for k in range(5):
            feed_policy(o, k * .1, 10 + .05 * k)
        feed_policy(o, .5, 10.2)
        self.assertAlmostEqual(o.recovery_evidence_s, .2)
        feed_policy(o, .6, 10.2)
        self.assertAlmostEqual(o.recovery_evidence_s, 0.)

    def test_pair_disagreement_cannot_earn_dynamic_evidence(self):
        o = policy_observer()
        for k in range(8):
            feed_policy(o, k * .1, 10 + .05 * k, gap=.3)
        self.assertEqual(o.recovery_evidence_s, 0.)

    def test_opposite_acceleration_cannot_earn_evidence(self):
        o = policy_observer()
        for k in range(8):
            feed_policy(o, k * .1, 10 - .05 * k)
        self.assertEqual(o.recovery_evidence_s, 0.)

    def test_stale_controller_cannot_earn_evidence(self):
        o = policy_observer(); o._recovery_command_valid = False
        for k in range(8):
            feed_policy(o, k * .1, 10 + .05 * k)
        self.assertEqual(o.recovery_evidence_s, 0.)

    def test_invalid_pair_interval_clears_evidence(self):
        for interval in (0., -.1, .01, .3, .6):
            o = policy_observer()
            for k in range(5):
                feed_policy(o, k * .1, 10 + .05 * k)
            feed_policy(o, .4 + interval, 10.2)
            self.assertEqual(o.recovery_evidence_s, 0.)

    def test_hard_rejection_clears_evidence_and_zero_lock(self):
        for z in (0., 20.):
            o = policy_observer()
            for k in range(5):
                feed_policy(o, k * .1, 10 + .05 * k)
            self.assertIsNone(feed_policy(o, .5, z))
            self.assertEqual(o.recovery_evidence_s, 0.)

    def test_limit_is_bounded_and_pair_scaled(self):
        o = policy_observer()
        o.recovery_evidence_s = .4
        for dt, expected in ((0., 0.), (.05, .1125), (.1, .225), (.2, .225)):
            self.assertAlmostEqual(o._reacquire_limit(dt), expected)
        o.recovery_evidence_s = 0.
        self.assertEqual(o._reacquire_limit(.1), .15)

    def test_reset_and_fused_clear_evidence(self):
        o = policy_observer(); o.recovery_evidence_s = .4
        o.step(0., Sample(0., 0.), Sample(0., 5.), Sample(0., 5.))
        self.assertEqual(o.recovery_evidence_s, 0.)
        o.recovery_evidence_s = .4
        o.reset()
        self.assertEqual(o.recovery_evidence_s, 0.)
        self.assertFalse(o._recovery_command_valid)

    def test_held_ticks_do_not_earn_or_apply_recovery(self):
        o = policy_observer()
        o.step(0., Sample(0., 1.), Sample(0., 10.), Sample(0., 10.))
        for i in range(1, 5):
            e = o.step(i * .05, Sample(0., 1.), Sample(0., 10.), Sample(0., 10.))
            self.assertNotEqual(e.mode, 'REACQUIRING')
            self.assertEqual(o.recovery_evidence_s, 0.)

    def test_future_and_nonfinite_never_used(self):
        o = policy_observer()
        e = o.step(0., Sample(1., 1.), Sample(.1, 10.), Sample(0., float('nan')))
        self.assertTrue(e.command_stale)
        self.assertEqual(o.used, [None, None])
        self.assertEqual(o.recovery_evidence_s, 0.)

    def test_constant_memory_shape(self):
        o = policy_observer()
        names = set(vars(o))
        for i in range(5000):
            t = i * .05
            o.step(t, Sample(t, 0.), Sample(t, 5.), Sample(t, 5.))
        self.assertEqual(set(vars(o)), names)
        for key in set(vars(o)) - set(vars(Observer())):
            self.assertIsInstance(getattr(o, key), (float, bool))

    def test_dynamic_common_mode_is_explicitly_ambiguous(self):
        # A false but dynamically model-consistent offset has the SAME allowed
        # input history as a recovered wheel pair after model drift. This probe
        # documents a limitation; it is NOT a protection claim or accuracy win.
        true_recovery, false_offset = policy_observer(), policy_observer()
        for k in range(5):
            a = feed_policy(true_recovery, k * .1, 10 + .05 * k)
            b = feed_policy(false_offset, k * .1, 10 + .05 * k)
            self.assertEqual(a, b)
        self.assertIsNotNone(a)


if __name__ == '__main__':
    unittest.main()
