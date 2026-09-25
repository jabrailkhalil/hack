"""Mechanism/invariant tests only: not evidence of real-data accuracy gain."""
from dataclasses import asdict
import hashlib
import importlib.util
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import types
import unittest

from reserve_odometry.core import Config, Observer, Sample

BASELINE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
CORE = 'src/reserve_odometry/reserve_odometry/core.py'
BASELINE_SHA256 = '780ca4796d86b4fa4e8c8679abfb73f58f23e003d4ee644ba964ffdeac9f0bfc'


def original_module():
    # Local byte-verified fixture or the pinned Git object; never a current main.
    fixture = os.environ.get('H05_BASELINE_CORE')
    raw = Path(fixture).read_bytes() if fixture else subprocess.check_output(
        ['git', 'show', BASELINE + ':' + CORE])
    if hashlib.sha256(raw).hexdigest() != BASELINE_SHA256:
        raise AssertionError('Not the pinned baseline core')
    module = types.ModuleType('h05_test_baseline')
    sys.modules[module.__name__] = module
    exec(compile(raw, '<pinned baseline>', 'exec'), module.__dict__)
    return module


BASE = original_module()


def observer(enabled=True):
    return Observer(Config(adaptation_tau_s=.5, h05_history_s=2. if enabled else 0.))


class ReliabilityTests(unittest.TestCase):
    def record(self, o, t, index=0, status='RANGE', accepted=()):
        raw = [None, None]; statuses = ['MISSING_OR_STALE'] * 2
        raw[index] = Sample(t, 50. if status == 'RANGE' else 6.)
        statuses[index] = status
        return o._reliability(t, raw, statuses, accepted)

    def weight(self, o, t):
        return o._reliability(t, (None, None), ('MISSING_OR_STALE',) * 2, ())

    def test_one_good_sample_does_not_reset(self):
        o = observer(); self.assertEqual(self.record(o, 1.), [.5, 1.])
        q = o._reliability(1.1, (Sample(1.1, 5.), Sample(1.1, 5.)),
                           ('CANDIDATE',) * 2, [0, 1])
        self.assertGreater(q[0], .5); self.assertLess(q[0], 1.)
        self.assertEqual(q[1], 1.)

    def test_exact_finite_expiry(self):
        o = observer(); self.record(o, 1.)
        self.assertLess(self.weight(o, 2.999)[0], 1.)
        self.assertEqual(self.weight(o, 3.), [1., 1.])
        self.assertEqual(len(o.h05_events[0]), 0)

    def test_linear_age_not_prediction_tick_count(self):
        a, b = observer(), observer(); self.record(a, 0.); self.record(b, 0.)
        for k in range(1, 20): self.weight(a, k * .05)
        self.assertEqual(self.weight(a, 1.), self.weight(b, 1.))
        self.assertAlmostEqual(self.weight(a, 1.)[0], 2. / 3.)

    def test_duplicate_range_counted_once(self):
        o = observer(); sample = Sample(0., 50.)
        for k in range(5):
            o._reliability(k * .05, (sample, None), ('RANGE', 'MISSING_OR_STALE'), ())
        self.assertEqual(list(o.h05_events[0]), [0.])

    def test_history_and_penalty_bounded(self):
        o = observer()
        for k in range(10000): self.record(o, k * .001)
        self.assertEqual(len(o.h05_events[0]), 4)
        self.assertEqual(o.h05_events[0].maxlen, 4)
        self.assertEqual(self.weight(o, 9.999)[0], .25)
        self.assertEqual(self.weight(o, 11.999), [1., 1.])

    def test_future_stale_nonfinite_not_evidence(self):
        o = observer()
        for sample in (None, Sample(2., 50.), Sample(0., 50.),
                       Sample(float('nan'), 50.), Sample(1., float('nan'))):
            self.assertEqual(o._reliability(1., (sample, None), ('RANGE',) * 2, ()), [1., 1.])
        self.assertEqual(o.h05_seen, [None, None])

    def test_old_sample_not_evidence(self):
        o = observer()
        o._reliability(1., (Sample(1., 5.), None), ('CANDIDATE', 'MISSING_OR_STALE'), [0])
        self.assertEqual(o._reliability(1.1, (Sample(.9, 50.), None), ('RANGE',) * 2, ()), [1., 1.])

    def test_common_model_drift_not_attributed(self):
        o = observer()
        for k in range(20):
            t = k * .1
            q = o._reliability(t, (Sample(t, 5.), Sample(t, 5.)), ('MODEL_DISAGREEMENT',) * 2, ())
            self.assertEqual(q, [1., 1.])

    def test_ambiguous_pair_without_anchor_not_attributed(self):
        o = observer()
        q = o._reliability(0., (Sample(0., 4.), Sample(0., 6.)), ('AMBIGUOUS_PAIR',) * 2, ())
        self.assertEqual(q, [1., 1.])

    def test_channel_attribution_requires_accepted_other(self):
        for status in ('MODEL_DISAGREEMENT', 'AMBIGUOUS_PAIR'):
            with self.subTest(status=status):
                o = observer(); self.assertEqual(self.record(o, 0., status=status, accepted=[1]), [.5, 1.])
                self.assertEqual(self.record(o, .1, index=1, status=status), self.weight(o, .1))
                self.assertEqual(len(o.h05_events[1]), 0)

    def test_rate_anomaly_is_local_evidence(self):
        o = observer(); self.assertEqual(self.record(o, 0., index=1, status='RATE_ANOMALY'), [1., .5])

    def test_reset_clears_history_and_timestamp(self):
        o = observer(); self.record(o, 100.); o.reset(velocity=5.)
        self.assertEqual(o.h05_seen, [None, None]); self.assertEqual(self.weight(o, 0.), [1., 1.])
        self.assertEqual(self.record(o, 0.), [.5, 1.])

    def test_flickering_channel_not_full_weight(self):
        o = observer()
        for k in range(20):
            t = k * .2; self.record(o, t)
            q = o._reliability(t + .1, (Sample(t + .1, 5.), None), ('CANDIDATE', 'MISSING_OR_STALE'), [0])
            self.assertLess(q[0], .6); self.assertGreaterEqual(q[0], .25)

    def test_disabled_matches_exact_baseline_in_fault_sequences(self):
        a = observer(False); b = BASE.Observer(BASE.Config(adaptation_tau_s=.5)); rng = random.Random(105)
        held = [None, None]
        for k in range(1200):
            t = k * .05
            if k % 2 == 0:
                for i in range(2):
                    value = 5. + .1 * math.sin(t)
                    x = rng.randrange(100)
                    held[i] = None if x < 4 else Sample(t, 50. if x < 7 else value + (5. if x < 10 else 0.))
            args = (t, Sample(t, .1 * math.sin(t / 10)), *held)
            self.assertEqual(asdict(a.step(*args)), asdict(b.step(*args)))
        self.assertEqual([len(x) for x in a.h05_events], [0, 0])

    def test_enabled_clean_matches_exact_baseline(self):
        a = observer(); b = BASE.Observer(BASE.Config(adaptation_tau_s=.5))
        for k in range(200):
            t = k * .1; v = 5. + .1 * math.sin(t)
            args = (t, Sample(t, 0.), Sample(t, v), Sample(t, v))
            self.assertEqual(asdict(a.step(*args)), asdict(b.step(*args)))

    def test_bootstrap_records_local_anomaly(self):
        o = observer()
        o.step(0., Sample(0., 0.), Sample(0., 50.), Sample(0., 5.))
        e = o.step(.1, Sample(.1, 0.), Sample(.1, 5.), Sample(.1, 5.))
        self.assertEqual(e.mode, 'INITIALIZED')
        self.assertLess(self.weight(o, .1)[0], 1.)

    def test_integrated_rate_fault_followed_by_accepted_pair(self):
        o = observer()
        for k, front in enumerate([5., 8., 5., 5.2]):
            t = k * .1
            e = o.step(t, Sample(t, 0.), Sample(t, front), Sample(t, 5.))
        self.assertEqual(e.mode, 'FUSED')
        self.assertEqual(len(o.h05_events[0]), 2)
        self.assertLess(self.weight(o, .3)[0], 1.)
        self.assertEqual(self.weight(o, .3)[1], 1.)

    def test_weighted_pair_favours_healthy_channel_and_inflates_r(self):
        a, b = observer(), observer(False)
        a.reset(velocity=5.); b.reset(velocity=5.); self.record(a, 0.)
        args = (.1, Sample(.1, 0.), Sample(.1, 5.2), Sample(.1, 5.))
        ea, eb = a.step(*args), b.step(*args)
        self.assertEqual(ea.mode, 'FUSED'); self.assertLess(ea.v, eb.v)
        self.assertGreater(ea.variance_v, eb.variance_v)
        q = 1. / 1.95; r = .01 * 2. / (1. + q)
        z = (q * 5.2 + 5.) / (1. + q)
        self.assertAlmostEqual(ea.v, 5. + (z - 5.) / (1. + r))

    def test_single_wheel_preserves_target_but_reduces_gain(self):
        a, b = observer(), observer(False)
        a.reset(velocity=5.); b.reset(velocity=5.); self.record(a, 0.)
        args = (.1, Sample(.1, 0.), Sample(.1, 5.2), None)
        ea, eb = a.step(*args), b.step(*args)
        self.assertEqual(ea.mode, 'SINGLE_WHEEL'); self.assertLess(ea.v, eb.v)
        self.assertAlmostEqual(ea.v, 5. + .2 / (1. + .04 * 1.95))

    def test_correlated_pair_has_no_independence_bonus(self):
        o = observer(); o.reset(velocity=5.)
        self.record(o, 0.); self.record(o, 0., index=1)
        e = o.step(.1, Sample(.1, 0.), Sample(.1, 5.2), Sample(.1, 5.2))
        self.assertAlmostEqual(e.v, 5. + .2 / (1. + .01 * 1.95))

    def test_reacquisition_equal_when_common_drift(self):
        a = observer(); b = BASE.Observer(BASE.Config(adaptation_tau_s=.5))
        a.reset(velocity=10.); b.reset(velocity=10.)
        modes = set()
        for k in range(60):
            t = k * .1; args = (t, Sample(t, 0.), Sample(t, 5.), Sample(t, 5.))
            ea, eb = a.step(*args), b.step(*args); modes.add(ea.mode)
            self.assertEqual(asdict(ea), asdict(eb))
        self.assertIn('REACQUIRING', modes)
        self.assertEqual([len(x) for x in a.h05_events], [0, 0])

    def test_invalid_clock_does_not_mutate_history(self):
        o = observer(); o.step(1., Sample(1., 0.), Sample(1., 5.), Sample(1., 5.))
        for t in (1., .9, float('nan'), 2.):
            with self.assertRaises(ValueError): o.step(t, front=Sample(t, 50.))
        self.assertEqual([len(x) for x in o.h05_events], [0, 0])

    def test_front_rear_symmetry(self):
        a, b = observer(), observer(); a.reset(velocity=5.); b.reset(velocity=5.)
        self.record(a, 0.); self.record(b, 0., index=1)
        ea = a.step(.1, Sample(.1, 0.), Sample(.1, 5.2), Sample(.1, 5.))
        eb = b.step(.1, Sample(.1, 0.), Sample(.1, 5.), Sample(.1, 5.2))
        self.assertEqual(ea.v, eb.v); self.assertEqual(ea.variance_v, eb.variance_v)

    def test_configuration_validation(self):
        for key, value in [('h05_history_s', -1.), ('h05_history_s', float('nan')),
                           ('h05_history_s', float('inf')), ('h05_min_reliability', 0.),
                           ('h05_min_reliability', 1.1), ('h05_min_reliability', float('nan'))]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): Config(**{key: value})


if __name__ == '__main__': unittest.main()
