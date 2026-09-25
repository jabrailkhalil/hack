"""Regression cases missed by equal-rate, synchronous sensor smoke tests."""
import math
import unittest
from reserve_odometry.core import Observer, Sample
from reserve_odometry.timeline import Timeline


class FinalRuntimeTests(unittest.TestCase):
    def test_asynchronous_wheels_can_initialize(self):
        o = Observer()
        e = o.step(0., Sample(0., 0.), Sample(0., 5.), None)
        self.assertEqual(e.mode, 'WAITING_FOR_INITIALIZATION')
        e = o.step(.05, Sample(.05, 0.), Sample(0., 5.), Sample(.05, 5.))
        self.assertEqual(e.mode, 'INITIALIZED')
        self.assertAlmostEqual(e.v, 5.)

    def test_reacquisition_survives_prediction_ticks(self):
        o = Observer()
        seen = []
        for i in range(241):
            t = i * .05
            ts = (i // 2) * .1  # 10 Hz wheels, 20 Hz estimator
            z = 5. if ts < 1. else 10.
            e = o.step(t, Sample(t, 0.), Sample(ts, z), Sample(ts, z))
            seen.append(e.mode)
        self.assertIn('REACQUIRING', seen)
        self.assertGreater(e.v, 9.5)

    def test_reacquisition_with_alternating_wheel_updates(self):
        o = Observer()
        wheels = [None, None]
        seen = []
        for i in range(281):
            t = i * .05
            wheels[i % 2] = Sample(t, 5. if t < 1. else 10.)
            e = o.step(t, Sample(t, 0.), *wheels)
            seen.append(e.mode)
        self.assertIn('REACQUIRING', seen)
        self.assertGreater(e.v, 9.5)

    def test_no_reacquisition_from_repeated_same_pair(self):
        o = Observer(); o.reset(velocity=5.)
        for i in range(60):
            t = i * .05
            e = o.step(t, Sample(t, 0.), Sample(0., 10.), Sample(0., 10.))
            self.assertNotEqual(e.mode, 'REACQUIRING')
        self.assertLess(e.v, 5.1)

    def test_invalid_range_cannot_advance_clock(self):
        timeline = Timeline()
        timeline.ingest(0, Sample(1., 0.))
        self.assertFalse(timeline.ingest(1, Sample(100., 1e6)))
        self.assertEqual(timeline.latest, 1.)

    def test_grid_has_no_cumulative_float_drift(self):
        timeline = Timeline(rate_hz=20., delay_s=0.)
        epoch = 1_790_000_000.
        for ch, z in ((0, 0.), (1, 5.), (2, 5.)):
            timeline.ingest(ch, Sample(epoch, z))
        list(timeline.advance(epoch))
        for i in range(1, 20001):
            now = epoch + i * .05
            timeline.ingest(0, Sample(now, 0.))
            list(timeline.advance(now))
        self.assertLess(abs(timeline.observer.t - (epoch + 1000.)), 1e-6)

    def test_rate_cannot_exceed_observer_step_limit(self):
        from reserve_odometry.core import Config
        with self.assertRaises(ValueError):
            Timeline(Observer(Config(max_step_s=.01)), rate_hz=20.)

if __name__ == '__main__':
    unittest.main()
