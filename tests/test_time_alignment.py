"""Analytic, compatibility and fault tests for the opt-in timestamp profile."""
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import types
import unittest
from unittest.mock import patch
import zipfile
import test_core
from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.timeline import Timeline

ROOT = Path(__file__).resolve().parents[1]


def baseline():
    """The delivered core is byte-identical to core.py at main 2f785136."""
    with zipfile.ZipFile(ROOT / 'submission/dist/reserve-odometry-v4.zip') as archive:
        raw = archive.read('reserve-odometry-v4/src/reserve_odometry/reserve_odometry/core.py')
    digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if digest != 'f6fc8ecd0b4e16018d814407b1944ce26ea550b0':
        raise ValueError('Not the pinned main estimator')
    mod = types.ModuleType('time_alignment_test_baseline')
    sys.modules[mod.__name__] = mod
    exec(compile(raw, '<pinned-main-core>', 'exec'), mod.__dict__)
    return mod


class TimeAlignmentTests(unittest.TestCase):
    def test_parameter_bounds(self):
        for value in (-.01, 1.01, math.nan, math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Config(wheel_time_compensation=value)
        for value in (0., .5, 1.):
            self.assertEqual(Config(wheel_time_compensation=value).wheel_time_compensation, value)

    def test_disabled_is_exactly_main_on_jitter_and_faults(self):
        old = baseline()
        rng = random.Random(615)
        for tau in (8., .5):
            a = old.Observer(old.Config(adaptation_tau_s=tau))
            b = Observer(Config(adaptation_tau_s=tau, wheel_time_compensation=0.))
            held = [None, None]
            for i in range(1600):
                t = i * .05
                for ch in range(2):
                    if rng.random() < .55:
                        held[ch] = Sample(t - rng.uniform(0, .04), 5 + .3 * math.sin(t) + rng.gauss(0, .03))
                    if 400 <= i < 500:
                        held[ch] = None
                    if 700 <= i < 730 and ch == 0:
                        held[ch] = Sample(t, 20.)
                command = Sample(t, .2 * math.sin(t / 2)) if i % 13 else None
                self.assertEqual(asdict(a.step(t, command, *held)), asdict(b.step(t, command, *held)))

    def test_constant_acceleration_delay_bias_is_removed(self):
        # Independent analytic oracle: v(t)=v0+a*t; no measured GNSS involved.
        for acceleration in (-.4, .6):
            errors = []
            for enabled in (0., 1.):
                o = Observer(Config(wheel_time_compensation=enabled))
                o.drive_target = lambda u, v: acceleration
                o.resistance = lambda v: 0.
                o.reset(velocity=10.)
                o.drive_a = acceleration
                for i in range(201):
                    t = i * .05
                    ts = t if i == 0 else t - .04
                    wheel = Sample(ts, 10. + acceleration * ts)
                    e = o.step(t, Sample(t, 1.), wheel, wheel)
                errors.append((abs(e.v - (10. + acceleration * t)),
                               abs(e.s - (10. * t + .5 * acceleration * t * t))))
            self.assertGreater(errors[0][0], .01)
            self.assertGreater(errors[0][1], .1)
            self.assertLess(errors[1][0], 1e-11)
            self.assertLess(errors[1][1], 1e-10)

    def test_age_adds_uncertainty_and_preserves_raw_samples(self):
        variances = []
        for age in (0., .1):
            o = Observer(Config(wheel_time_compensation=1.))
            o.drive_target = lambda u, v: 1.
            o.resistance = lambda v: 0.
            o.reset(velocity=5.1)
            o.drive_a = 1.
            wheel = Sample(.1 - age, 5.1 - age)
            e = o.step(.1, Sample(.1, 1.), wheel, wheel)
            self.assertAlmostEqual(e.v, 5.1)
            self.assertEqual(o.raw_previous, [wheel, wheel])
            self.assertEqual(o.used, [wheel.t, wheel.t])
            variances.append(e.variance_v)
        self.assertGreater(variances[1], variances[0])

    def test_old_measurement_is_not_assimilated_twice(self):
        o = Observer(Config(wheel_time_compensation=1.))
        o.step(0., Sample(0., 0.), Sample(0., 5.), Sample(0., 5.))
        first = o.step(.05, Sample(.05, 0.), Sample(.02, 5.), Sample(.02, 5.))
        again = o.step(.1, Sample(.1, 0.), Sample(.02, 5.), Sample(.02, 5.))
        self.assertEqual(again.mode, 'MODEL_ONLY')
        self.assertEqual(again.front_status, 'DUPLICATE_OR_OLD')
        self.assertGreater(again.variance_v, first.variance_v)

    def test_future_inputs_do_not_change_past_outputs(self):
        def replay(changed):
            timeline = Timeline(Observer(Config(wheel_time_compensation=1.)), 20., 0.)
            result = []
            for i in range(101):
                t = i * .05
                for ch in range(3):
                    value = .2 if ch == 0 else (18. if changed and t > 2. else 5.)
                    timeline.ingest(ch, Sample(t, value))
                    for estimate, held in timeline.advance():
                        self.assertTrue(all(s is None or s.t <= estimate.t + 1e-9 for s in held))
                        if estimate.t <= 2.:
                            result.append(asdict(estimate))
            return result
        self.assertEqual(replay(False), replay(True))

    def test_yaml_matches_measured_config(self):
        cfg = ROOT / 'src/reserve_odometry/config'
        expected = json.loads((cfg / 'time_aligned_v6.json').read_text())['config']
        actual = {}
        for line in (cfg / 'time_aligned_v6.yaml').read_text().splitlines():
            key, sep, value = line.strip().partition(':')
            if sep and key.startswith('model.'):
                actual[key[6:]] = float(value)
        self.assertEqual(actual, asdict(Config(**expected)))
        self.assertEqual(actual['wheel_time_compensation'], 1.)
        self.assertEqual(Config().wheel_time_compensation, 0.)


class TimeAlignedProfileTests(test_core.ObserverTests):
    """Repeat all existing observer fault scenarios with the measured profile."""
    def setUp(self):
        cfg = json.loads((ROOT / 'src/reserve_odometry/config/time_aligned_v6.json').read_text())['config']
        def selected(config=None):
            return Observer(config if config is not None else Config(**cfg))
        self.mock = patch.object(test_core, 'Observer', selected)
        self.mock.start()
        self.addCleanup(self.mock.stop)
