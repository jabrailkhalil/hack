"""Experiment-only tests; apply the tracked patch before running these."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src/reserve_odometry'))
from reserve_odometry.core import Config, Observer, Sample


class ProjectionTests(unittest.TestCase):
    def test_validates_gain(self):
        for gain in (-1., 1.001, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                Config(wheel_projection_gain=gain)

    def test_zero_age_is_identical(self):
        a, b = Observer(), Observer(Config(wheel_projection_gain=1.))
        for i in range(100):
            t=i*.05
            inputs=(t,Sample(t,.1),Sample(t,5.),Sample(t,5.))
            self.assertEqual(asdict(a.step(*inputs)), asdict(b.step(*inputs)))

    def test_projects_only_correction_without_mutating_raw_samples(self):
        observers=[Observer(Config(wheel_projection_gain=g)) for g in (0.,1.)]
        for o in observers:
            o.reset(velocity=5.);o.step(1.,Sample(1.,.5))
        stamp=1.01;f=Sample(stamp,5.);r=Sample(stamp,5.)
        old=observers[0].step(1.05,Sample(1.05,.5),f,r)
        new=observers[1].step(1.05,Sample(1.05,.5),f,r)
        self.assertGreater(new.v,old.v)
        self.assertEqual(observers[1].used,[stamp,stamp])
        self.assertEqual(observers[1].raw_previous,[f,r])
        e=observers[1].step(1.1,Sample(1.1,.5),f,r)
        self.assertEqual(e.front_status,'DUPLICATE_OR_OLD')

    def test_future_does_not_update(self):
        o=Observer(Config(wheel_projection_gain=1.));o.reset(velocity=5.)
        e=o.step(1.,Sample(1.,.5),Sample(1.01,5.),Sample(1.01,5.))
        self.assertEqual(o.used,[None,None]);self.assertEqual(e.mode,'MODEL_ONLY')

    def test_raw_rate_gate_is_preserved(self):
        o=Observer(Config(wheel_projection_gain=1.))
        o.step(1.,Sample(1.,0.),Sample(1.,5.),Sample(1.,5.))
        e=o.step(1.05,Sample(1.05,.5),Sample(1.01,15.),Sample(1.01,15.))
        self.assertEqual(e.front_status,'RATE_ANOMALY')
        self.assertEqual(e.rear_status,'RATE_ANOMALY')


if __name__=='__main__':unittest.main()
