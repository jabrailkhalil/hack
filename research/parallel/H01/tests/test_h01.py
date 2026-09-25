"""Structural tests, not evidence of real-bag accuracy improvement."""
from dataclasses import asdict
import importlib.util
import math
import os
from pathlib import Path
import random
import sys
import unittest

from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.h01_projection import ConditionalProjection


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.c = Config(h01_projection_gain=1.0, adaptation_tau_s=0.5)
        self.gate = ConditionalProjection()

    def pair(self, stamp, *, acceleration=0.5, **kw):
        v = 3.0 + acceleration*stamp
        samples = kw.pop('samples', [Sample(stamp, v), Sample(stamp, v)])
        args = dict(c=self.c, t=stamp+0.05, a_model=acceleration,
                    predicted=v+acceleration*0.05, disturbance=0.0,
                    samples=samples, accepted=[0, 1],
                    statuses=['CANDIDATE', 'CANDIDATE'], command_stale=False)
        args.update(kw)
        return self.gate.delta(**args)

    def warm(self, acceleration=0.5):
        return [self.pair(k*0.1, acceleration=acceleration) for k in range(9)]

    def test_requires_history_and_dwell(self):
        deltas = self.warm()
        self.assertEqual(deltas[:6], [0.0]*6)
        self.assertAlmostEqual(deltas[6], 0.025)
        self.assertAlmostEqual(deltas[-1], 0.025)

    def test_half_gain(self):
        self.c.h01_projection_gain = 0.5
        self.assertAlmostEqual(self.warm()[-1], 0.0125)

    def test_braking_projects_backwards(self):
        self.assertAlmostEqual(self.warm(-0.5)[-1], -0.025)

    def test_disabled(self):
        self.c.h01_projection_gain = 0.0
        self.assertEqual(self.warm(), [0.0]*9)
        self.assertIsNone(self.gate.previous)

    def test_duplicate_tick_preserves_but_does_not_project(self):
        self.warm()
        previous, since = self.gate.previous, self.gate.since
        delta = self.gate.delta(self.c, 0.88, 0.5, 3.44, 0,
                                [None, None], [], ['DUPLICATE_OR_OLD']*2, False)
        self.assertEqual(delta, 0)
        self.assertIs(self.gate.previous, previous)
        self.assertEqual(self.gate.since, since)
        self.assertAlmostEqual(self.pair(0.9), 0.025)

    def test_expired_duplicate_history_clears(self):
        self.warm()
        self.gate.delta(self.c, 1.1, 0.5, 3.5, 0,
                        [None, None], [], ['DUPLICATE_OR_OLD']*2, False)
        self.assertIsNone(self.gate.previous)
        self.assertIsNone(self.gate.since)

    def test_rejections_restart_trust(self):
        for reason, args in [
            ('COMMAND', dict(command_stale=True)),
            ('NOT_TRUSTED_PAIR', dict(accepted=[0])),
            ('NOT_TRUSTED_PAIR', dict(accepted=[], statuses=['MODEL_DISAGREEMENT']*2)),
            ('AGE_OR_SKEW', dict(t=1.01)),
            ('AGE_OR_SKEW', dict(t=0.89)),
            ('INNOVATION', dict(predicted=10)),
            ('MODEL_SATURATION', dict(a_model=3)),
            ('MODEL_SATURATION', dict(disturbance=0.6)),
            ('NONFINITE', dict(a_model=float('nan'))),
        ]:
            with self.subTest(reason=reason, args=args):
                self.gate = ConditionalProjection()
                self.warm()
                self.assertEqual(self.pair(0.9, **args), 0)
                self.assertEqual(self.gate.last_reason, reason)
                self.assertIsNone(self.gate.since)
                self.assertIsNone(self.gate.previous)
                self.assertEqual(self.pair(1.0), 0)

    def test_slow_or_locked_pair_not_projected(self):
        for value in (0, 0.25, 0.5):
            self.warm()
            self.assertEqual(self.pair(0.9, samples=[Sample(.9, value)]*2), 0)
            self.assertEqual(self.gate.last_reason, 'WHEEL_CONFIDENCE')

    def test_strict_pair_disagreement(self):
        self.warm()
        self.assertEqual(self.pair(.9, samples=[Sample(.9, 3.45), Sample(.9, 3.80)]), 0)
        self.assertEqual(self.gate.last_reason, 'WHEEL_CONFIDENCE')

    def test_bad_acceleration_not_replaced_by_average(self):
        self.warm()
        # Average agrees with the model; the separate wheel slopes do not.
        self.assertEqual(self.pair(.9, samples=[Sample(.9, 3.51), Sample(.9, 3.39)]), 0)
        self.assertEqual(self.gate.last_reason, 'ACCELERATION')
        self.assertIsNone(self.gate.since)

    def test_model_acceleration_mismatch(self):
        self.warm()
        self.assertEqual(self.pair(.9, a_model=-1), 0)
        self.assertEqual(self.gate.last_reason, 'ACCELERATION')

    def test_history_gap(self):
        self.warm()
        self.assertEqual(self.pair(1.2), 0)
        self.assertEqual(self.gate.last_reason, 'HISTORY_GAP')

    def test_no_mutation_and_bounded_state(self):
        self.warm()
        pair = [Sample(.9, 3.45), Sample(.9, 3.45)]
        before = list(pair)
        self.pair(.9, samples=pair)
        self.assertEqual(pair, before)
        self.assertEqual(len(self.gate.previous), 2)
        self.assertFalse(hasattr(self.gate, '__dict__'))

    def test_delta_limit_and_speed_bounds(self):
        self.c.rate_noise_margin_mps = 0.001
        self.assertAlmostEqual(self.warm()[-1], 0.001)
        self.c.max_speed_mps = 3.45
        self.assertEqual(self.pair(.9), 0)
        self.assertEqual(self.gate.last_reason, 'PROJECTION_BOUNDS')

    def test_observer_reset_discards_projection_history(self):
        observer = Observer(self.c)
        observer.h01_projection = self.gate
        self.warm()
        observer.reset()
        self.assertIsNone(observer.h01_projection.previous)
        self.assertIsNone(observer.h01_projection.since)

    def test_config_rejects_invalid_gain(self):
        for gain in (-0.1, 1.1, float('nan'), float('inf')):
            with self.subTest(gain=gain), self.assertRaises(ValueError):
                Config(h01_projection_gain=gain)

    def test_bootstrap_and_future_samples_are_not_projected(self):
        observer = Observer(self.c)
        result = observer.step(0, Sample(0, 0.2), Sample(.1, 3), Sample(.1, 3))
        self.assertEqual(result.mode, 'WAITING_FOR_INITIALIZATION')
        self.assertIsNone(observer.h01_projection.previous)
        result = observer.step(.1, Sample(.1, .2), Sample(.1, 3), Sample(.1, 3))
        self.assertEqual(result.mode, 'INITIALIZED')
        self.assertEqual(result.v, 3)
        self.assertIsNone(observer.h01_projection.previous)

    def test_actual_observer_uses_projection_without_mutating_samples(self):
        observer = Observer(self.c)
        used = 0
        for k in range(201):
            t = k*.05
            stamp = max(0, (k//2)*.1-.02)
            v = 3+.5*stamp
            front, rear = Sample(stamp, v), Sample(stamp, v)
            observer.step(t, Sample(t, .55), front, rear)
            self.assertEqual(front.value, v)
            self.assertEqual(rear.value, v)
            if observer.h01_projection.last_delta:
                used += 1
        self.assertGreater(used, 0)

    def test_disabled_observer_exactly_matches_frozen_source(self):
        source = os.environ.get('H01_BASELINE_CORE')
        if not source:
            self.skipTest('set H01_BASELINE_CORE to the git-show baseline core.py')
        spec = importlib.util.spec_from_file_location('h01_frozen_core', source)
        old = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = old
        spec.loader.exec_module(old)
        a = Observer(Config(adaptation_tau_s=.5))
        b = old.Observer(old.Config(adaptation_tau_s=.5))
        rng = random.Random(101)
        for k in range(10000):
            t = k*.05
            stamp = (k//2)*.1
            v = max(0, 5+4*math.sin(stamp*.03))
            u = .6*math.sin(t*.017)
            f, r = Sample(stamp, v), Sample(stamp, v)
            phase = k % 1000
            if 200 <= phase < 260:
                f = Sample(stamp, v+5)
            if 400 <= phase < 460:
                f = r = None
            if 600 <= phase < 660:
                f = r = Sample(stamp, 0)
            command = Sample(t, u) if rng.random() > .01 else None
            self.assertEqual(asdict(a.step(t, command, f, r)), asdict(b.step(t, command, f, r)))


if __name__ == '__main__':
    unittest.main()
