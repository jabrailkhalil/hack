"""Structural checks only: these do not establish accuracy on real bags."""
from dataclasses import asdict
import math
from pathlib import Path
import random
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'src/reserve_odometry')]
from build_candidate import candidate_module, candidate_source, sha_bytes, CANDIDATE_CORE_SHA256
from reserve_odometry import core as baseline
candidate = candidate_module()


class TimingUncertaintyTests(unittest.TestCase):
    def once(self, age=0.0, skew=0.0, single=False, enabled=True):
        config = candidate.Config(timing_accel_fraction=0.5 if enabled else 0.0)
        observer = candidate.Observer(config)
        observer.reset(velocity=5.0)
        observer.pv = 0.01
        front = candidate.Sample(1.0-age, 5.1)
        rear = None if single else candidate.Sample(1.0-age+skew, 5.1)
        estimate = observer.step(1.0, candidate.Sample(1.0, 0.0), front, rear)
        return estimate

    def test_exact_candidate_hash(self):
        self.assertEqual(sha_bytes(candidate_source()), CANDIDATE_CORE_SHA256)

    def test_config_bounds_and_nonfinite(self):
        for value in (-0.001, 1.001, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                candidate.Config(timing_accel_fraction=value)
        for value in (0.0, 0.5, 1.0):
            candidate.Config(timing_accel_fraction=value)

    def test_correlated_pair_has_no_one_over_n(self):
        self.assertAlmostEqual(self.once().v, 5.05, places=14)
        self.assertAlmostEqual(self.once().variance_v, 0.005, places=14)

    def test_age_formula_without_measurement_projection(self):
        for age in (0.0, 0.05, 0.1, 0.2, 0.25):
            r = 0.01 + 1.5**2 * age**2
            self.assertAlmostEqual(self.once(age=age).v, 5.0 + 0.01/(0.01+r)*0.1, places=14)

    def test_age_only_reduces_correction(self):
        values = [self.once(age=a).v for a in (0, 0.05, 0.1, 0.2)]
        self.assertTrue(all(a > b for a,b in zip(values, values[1:])))

    def test_skew_reduces_weight_at_same_max_age(self):
        a, b = self.once(age=0.1), self.once(age=0.1, skew=0.05)
        self.assertLess(b.v, a.v)
        r = 0.01 + 1.5**2 * (0.1**2 + 0.25*0.05**2)
        self.assertAlmostEqual(b.v, 5.0 + 0.01/(0.01+r)*0.1, places=14)

    def test_single_wheel_confidence_multiplies_all_uncertainty(self):
        r = 4.0 * (0.01 + 1.5**2 * 0.1**2)
        self.assertAlmostEqual(self.once(age=0.1, single=True).v, 5.0+0.01/(0.01+r)*0.1, places=14)

    def test_zero_age_skew_same_as_disabled(self):
        self.assertEqual(asdict(self.once()), asdict(self.once(enabled=False)))

    def test_future_and_stale_are_not_rescued_by_large_r(self):
        for stamp in (1.0001, 0.749):
            observer = candidate.Observer(candidate.Config(timing_accel_fraction=0.5))
            observer.reset(velocity=5.0)
            s = candidate.Sample(stamp, 5.1)
            e = observer.step(1.0, candidate.Sample(1.0, 0.0), s, s)
            self.assertEqual(e.mode, 'MODEL_ONLY')
            self.assertEqual(e.front_status, 'MISSING_OR_STALE')

    def test_duplicate_cannot_be_assimilated_twice(self):
        observer = candidate.Observer(candidate.Config(timing_accel_fraction=0.5))
        observer.reset(velocity=5.0)
        s = candidate.Sample(0.99, 5.1)
        observer.step(1.0, candidate.Sample(1.0, 0.0), s, s)
        e = observer.step(1.05, candidate.Sample(1.05, 0.0), s, s)
        self.assertEqual(e.mode, 'MODEL_ONLY')
        self.assertEqual(e.front_status, 'DUPLICATE_OR_OLD')

    def test_rejected_old_channel_does_not_inflate_accepted_channel(self):
        observer = candidate.Observer(candidate.Config(timing_accel_fraction=0.5))
        observer.reset(velocity=5.0)
        observer.pv = 0.01
        e = observer.step(1.0, candidate.Sample(1.0, 0.0),
                          candidate.Sample(0.8, 100.0), candidate.Sample(1.0, 5.1))
        self.assertEqual(e.front_status, 'RANGE')
        self.assertAlmostEqual(e.v, 5.02, places=14)

    def test_disabled_matches_pristine_core_over_faulted_stream(self):
        old = baseline.Observer(baseline.Config(adaptation_tau_s=0.5))
        off = candidate.Observer(candidate.Config(adaptation_tau_s=0.5, timing_accel_fraction=0.0))
        rng = random.Random(20260925)
        front = rear = None
        for i in range(6000):
            t = i*0.05
            speed = 5.0 + math.sin(t/4.0)
            if i % 2 == 0:
                front = baseline.Sample(t-rng.uniform(0, 0.04), speed+rng.uniform(-0.05, 0.05))
            if i % 3 == 0:
                rear = baseline.Sample(t-rng.uniform(0, 0.04), speed+rng.uniform(-0.05, 0.05))
            f = None if 1000 <= i < 1100 else front
            r = None if 1000 <= i < 1100 else rear
            if 2000 <= i < 2050:
                f = baseline.Sample(t, 0.0)
                r = baseline.Sample(t, 0.0)
            u = baseline.Sample(t, 0.2*math.sin(t/10))
            self.assertEqual(asdict(old.step(t,u,f,r)), asdict(off.step(t,u,f,r)))

    def test_state_does_not_grow(self):
        observer = candidate.Observer(candidate.Config(timing_accel_fraction=0.5))
        keys = set(vars(observer))
        for i in range(10000):
            t = i*0.05
            s = candidate.Sample(t, 5.0)
            e = observer.step(t, candidate.Sample(t, 0.0), s, s)
            self.assertTrue(math.isfinite(e.v) and math.isfinite(e.variance_v))
        self.assertEqual(set(vars(observer)), keys)
        for name in ('used', 'raw_previous', 'pair_pending'):
            self.assertEqual(len(getattr(observer, name)), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
