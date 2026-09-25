"""Experiment-only optional decay invariants; no real data used here."""
import unittest
from reserve_odometry.core import Config, Observer, Sample


class DecayTests(unittest.TestCase):
    def test_decay_only_after_lost_trusted_pair(self):
        o=Observer(Config(disturbance_decay_s=2.))
        o.reset(velocity=5.);o.step(1.,Sample(1.,0.),Sample(1.,5.),Sample(1.,5.))
        o.disturbance=.2
        o.step(1.1,Sample(1.1,0.))
        self.assertEqual(o.disturbance,.2)
        for i in range(2,12):
            o.step(1.+i*.1,Sample(1.+i*.1,0.))
        self.assertGreater(o.disturbance,0.)
        self.assertLess(o.disturbance,.2)

    def test_decay_disabled_preserves_legacy_hold(self):
        o=Observer();o.reset(velocity=5.)
        o.step(1.,Sample(1.,0.),Sample(1.,5.),Sample(1.,5.));o.disturbance=.2
        for i in range(1,20):o.step(1+i*.1,Sample(1+i*.1,0.))
        self.assertEqual(o.disturbance,.2)
