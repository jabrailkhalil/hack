import importlib.util
import math
from pathlib import Path
import random
import subprocess
import sys
import unittest
from unittest.mock import patch

from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.numerics_h08 import _mean_fraction, predict

ROOT = Path(__file__).resolve().parents[3]
BASE = '984fdf2fc4faf05325249215d6b8541c0e68209a'


class NumericalTests(unittest.TestCase):
    def test_fraction_limits(self):
        self.assertEqual(_mean_fraction(0.0), 0.0)
        for x in (1e-12, 1e-9, 1e-6):
            self.assertAlmostEqual(_mean_fraction(x) / x, 0.5 - x / 6, places=12)
        self.assertLess(abs(_mean_fraction(1e-4) - (0.5e-4 - 1e-8/6)), 1e-13)

    def test_invalid_arguments(self):
        for dt, tau in ((-1, .4), (float('nan'), .4), (.1, 0), (.1, float('inf'))):
            with self.assertRaises(ValueError):
                predict(dt, tau, 0, 2, 1, 0, lambda v: 0, 3, 40)
        for flag in (-1, 0.5, 2, float('nan')):
            with self.assertRaises(ValueError):
                Config(numerical_prediction=flag)

    def test_zero_step(self):
        self.assertEqual(predict(0, .4, .2, 5, 1, .1, lambda v: .3, 3, 40), (.2, 5))

    def test_exact_held_drive(self):
        for initial, target in ((0, 1), (1, -1), (-.5, .2)):
            drive, velocity, tau, h = initial, 5., .4, .05
            for _ in range(100):
                drive, velocity = predict(h, tau, drive, velocity, target, 0, lambda v: 0, 3, 40)
            duration = 100 * h
            expected = 5 + target * duration + (initial-target)*tau*(-math.expm1(-duration/tau))
            self.assertAlmostEqual(velocity, expected, places=12)
            self.assertAlmostEqual(drive, target+(initial-target)*math.exp(-duration/tau), places=12)

    def test_midpoint_linear_resistance_convergence(self):
        errors = []
        for steps in (20, 40, 80):
            drive, velocity = 0., 5.
            for _ in range(steps):
                drive, velocity = predict(1/steps, .4, drive, velocity, 0, 0, lambda v: .2*v, 3, 40)
            errors.append(abs(velocity - 5*math.exp(-.2)))
        self.assertGreater(errors[0]/errors[1], 3.9)
        self.assertGreater(errors[1]/errors[2], 3.9)

    def test_bounded_output_and_acceleration(self):
        for velocity in (-39.99, -.01, 0, .01, 39.99):
            for target in (-100, 100):
                _, v = predict(.05, .4, 0, velocity, target, .6, lambda v: 2*v, 3, 40)
                self.assertLessEqual(abs(v), 40)
                self.assertLessEqual(abs(v-velocity), .15+1e-12)

    def test_opt_out_matches_exact_baseline(self):
        import types
        module = types.ModuleType('h08_original_core')
        sys.modules[module.__name__] = module
        source = subprocess.check_output(['git', 'show', BASE + ':src/reserve_odometry/reserve_odometry/core.py'], cwd=ROOT)
        exec(compile(source, 'baseline/core.py', 'exec'), module.__dict__)
        old, new = module.Observer(module.Config(adaptation_tau_s=.5)), Observer(Config(adaptation_tau_s=.5))
        rng = random.Random(8)
        for i in range(4000):
            t = i*.05; stamp = (i//2)*.1
            z = 5+.4*math.sin(stamp)
            front = None if 300<i<450 else Sample(stamp, z+(5 if 800<i<900 else 0))
            rear = None if 300<i<450 else Sample(stamp, z)
            command = Sample(stamp, rng.uniform(-.3, .3))
            a, b = old.step(t, command, front, rear), new.step(t, command, front, rear)
            self.assertEqual(a.__dict__, b.__dict__)

    def test_candidate_future_inputs_and_memory(self):
        o = Observer(Config(numerical_prediction=1.0)); o.reset(velocity=5)
        state_names = set(vars(o))
        for i in range(4000):
            t = i*.05
            e = o.step(t, Sample(t+1, .5), Sample(t+1, 30), Sample(t+1, 30))
            self.assertTrue(e.command_stale)
            self.assertEqual(o.used, [None, None])
            self.assertTrue(all(math.isfinite(x) for x in (e.v, e.s, e.a)))
        self.assertEqual(set(vars(o)), state_names)
        self.assertTrue(all(len(v)<=2 for v in vars(o).values() if isinstance(v, (list, tuple))))

    def test_candidate_existing_observer_scenarios(self):
        spec = importlib.util.spec_from_file_location('h08_original_tests', ROOT/'tests/test_core.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        original = module.Observer
        def factory(config=None):
            config = config or Config()
            config.numerical_prediction = 1.0
            return original(config)
        result = unittest.TestResult()
        with patch.object(module, 'Observer', factory):
            unittest.defaultTestLoader.loadTestsFromTestCase(module.ObserverTests).run(result)
        self.assertEqual(result.testsRun, 20)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])


if __name__ == '__main__':
    unittest.main()
