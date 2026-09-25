"""Mechanism/causality tests only; these do not prove accuracy on recordings."""
from dataclasses import asdict
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import types
import unittest

from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.timeline import Timeline

BASELINE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
CORE = 'src/reserve_odometry/reserve_odometry/core.py'


def original_module():
    path = os.environ.get('H03_BASELINE_CORE')
    source = Path(path).read_text() if path else subprocess.check_output(
        ['git', 'show', BASELINE + ':' + CORE], text=True)
    module = types.ModuleType('_original_h03_baseline')
    sys.modules[module.__name__] = module
    exec(compile(source, '<pinned-baseline-core>', 'exec'), module.__dict__)
    return module


class H03Tests(unittest.TestCase):
    def observer(self, window=.4):
        return Observer(Config(adaptation_tau_s=.5, adaptation_window_s=window))

    def slope(self, observer, points):
        old = points[0]
        result = None
        for point in points[1:]:
            result = observer._wheel_acceleration(point.t, point.value, old)
            old = point
        return result

    def feed(self, observer, t, value=3., command=True, front=None, rear=None):
        return observer.step(t, Sample(t, .1) if command else None,
                             front or Sample(t, value), rear or Sample(t, value))

    def seeded(self):
        o = self.observer()
        for i in range(5):
            self.feed(o, i*.1, 3.+i*.01)
        self.assertGreaterEqual(len(o.adapt_history), 2)
        return o

    def test_configuration_domain(self):
        for value in [0., .05, .2, .3, .4]:
            Config(adaptation_window_s=value)
        for value in [-1., .001, .41, math.nan, math.inf]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                Config(adaptation_window_s=value)

    def test_affine_regular(self):
        for window in [.2, .3, .4]:
            points = [Sample(i*.1, 4.-.7*i*.1) for i in range(20)]
            self.assertAlmostEqual(self.slope(self.observer(window), points), -.7)

    def test_affine_irregular(self):
        points = [Sample(t, 3.+1.2*t) for t in [0., .07, .16, .23, .34, .41]]
        self.assertAlmostEqual(self.slope(self.observer(), points), 1.2)

    def test_five_point_common_outlier_is_not_independent_evidence(self):
        points = [Sample(i*.1, 3.+i*.1+(1. if i==4 else 0.)) for i in range(5)]
        self.assertAlmostEqual(self.slope(self.observer(), points), 1.)
        self.assertAlmostEqual(self.slope(self.observer(0), points), 11.)

    def test_two_points_do_not_wait_for_window(self):
        self.assertAlmostEqual(self.slope(self.observer(), [Sample(0.,3.),Sample(.1,3.1)]), 1.)

    def test_no_out_of_window_fallback(self):
        o = self.observer(.2)
        self.assertIsNone(self.slope(o, [Sample(0.,3.), Sample(.23,3.2)]))
        self.assertEqual(len(o.adapt_history), 1)

    def test_history_hard_cap_and_time_window(self):
        o = self.observer()
        old = Sample(0., 3.)
        for i in range(1, 10001):
            p = Sample(i*.051, 3.+math.sin(i*.01))
            o._wheel_acceleration(p.t, p.value, old)
            self.assertLessEqual(len(o.adapt_history), 7)
            self.assertTrue(all(0 <= p.t-s.t <= .4+1e-9 for s in o.adapt_history))
            old = p

    def test_explicit_reset_clears_history(self):
        o = self.seeded()
        o.reset()
        self.assertEqual(o.adapt_history, [])
        self.assertIsNone(o.adapt_previous)

    def test_duplicate_prediction_does_not_add_pair(self):
        o = self.seeded()
        before = list(o.adapt_history)
        e = o.step(.45, Sample(.4,.1), Sample(.4,3.04), Sample(.4,3.04))
        self.assertEqual(o.adapt_history, before)
        self.assertEqual(e.front_status, 'DUPLICATE_OR_OLD')

    def test_stale_command_clears_experimental_history(self):
        o = self.seeded()
        self.feed(o, .5, 3.05, command=False)
        self.assertEqual(o.adapt_history, [])
        self.assertIsNone(o.adapt_previous)

    def test_rejected_future_nonfinite_and_rate_samples_clear_history(self):
        for invalid in [Sample(.7,3.05), Sample(.5,math.nan), Sample(.5,50.), Sample(.5,8.)]:
            o = self.seeded()
            self.feed(o,.5,3.05,front=invalid)
            self.assertEqual(o.adapt_history, [])
            self.assertIsNone(o.adapt_previous)

    def test_disagreeing_pair_does_not_train(self):
        o = self.seeded()
        self.feed(o,.5,3.05,front=Sample(.5,3.55),rear=Sample(.5,2.55))
        self.assertEqual(o.adapt_history, [])

    def test_gap_never_bridges_old_pairs(self):
        o = self.seeded()
        o.step(.6, Sample(.6,.1), None, None)
        o.step(.8, Sample(.8,.1), None, None)
        self.feed(o,.9,3.08)
        self.assertLessEqual(len(o.adapt_history),1)
        self.assertTrue(all(p.t >= .9 for p in o.adapt_history))

    def test_disturbance_remains_bounded(self):
        o = self.observer()
        for i in range(500):
            t=i*.05
            e=self.feed(o,t,3.+.1*math.sin(3*t))
            self.assertTrue(math.isfinite(e.v))
            self.assertLessEqual(abs(e.disturbance),o.c.disturbance_limit_mps2)
            self.assertLessEqual(len(o.adapt_history),7)

    def test_disabled_matches_pinned_baseline_exactly(self):
        baseline = original_module()
        a, b = self.observer(0), baseline.Observer(baseline.Config(adaptation_tau_s=.5))
        rng = random.Random(30260925)
        for i in range(2000):
            t=i*.05
            value=3.+.2*math.sin(.3*t)+rng.uniform(-.03,.03)
            command=Sample(t,.1) if i%137 else None
            f=Sample(t,value) if i%89 else None
            r=Sample(t,value+.01) if i%73 else None
            if i%47==1: f=Sample(t-1.,value)
            if i%109==5: r=Sample(t+.1,value)
            if i%101==7: f=Sample(t,value+5.)
            convert=lambda s: baseline.Sample(s.t,s.value) if s else None
            self.assertEqual(asdict(a.step(t,command,f,r)),
                             asdict(b.step(t,convert(command),convert(f),convert(r))))
        self.assertEqual(a.adapt_history, [])

    def test_stream_prefix_is_suffix_independent(self):
        def run(length):
            tl=Timeline(self.observer(),rate_hz=20.,delay_s=0.)
            outputs=[]
            for i in range(length):
                t=i*.1
                for ch,value in [(0,.1),(1,3.+.05*math.sin(t)),(2,3.+.05*math.sin(t))]:
                    tl.ingest(ch,Sample(t,value))
                    for e,held in tl.advance():
                        self.assertTrue(all(s is None or s.t <= e.t+1e-9 for s in held))
                        outputs.append(asdict(e))
            return outputs
        short, long = run(100), run(200)
        self.assertEqual(short,long[:len(short)])


if __name__ == '__main__':
    unittest.main()
