"""H10 implementation checks only. Synthetic inputs do not establish real accuracy."""
import ast
from dataclasses import asdict
import importlib.util
import math
import os
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src/reserve_odometry'))
from reserve_odometry.core import Config, Observer, Sample

BASE_PATH = Path(os.environ.get('H10_BASELINE_CORE', '/tmp/H10-baseline-core.py'))
spec = importlib.util.spec_from_file_location('h10_unmodified_baseline', BASE_PATH)
baseline = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = baseline
spec.loader.exec_module(baseline)


def matmul(a, b):
    return [[sum(x * y for x, y in zip(row, col)) for col in zip(*b)] for row in a]


def transpose(a):
    return list(map(list, zip(*a)))


class JointTests(unittest.TestCase):
    def joint(self, **kwargs):
        return Observer(Config(joint_observer_enabled=1, adaptation_tau_s=.5, **kwargs))

    def psd(self, ob):
        self.assertTrue(all(math.isfinite(x) for x in (ob.v, ob.disturbance, ob.pv, ob.pd, ob.pvd)))
        self.assertGreaterEqual(ob.pv, 0.)
        self.assertGreaterEqual(ob.pd, 0.)
        self.assertGreaterEqual(ob.pv * ob.pd - ob.pvd ** 2, -1e-10)
        self.assertLessEqual(abs(ob.v), ob.c.max_speed_mps)
        self.assertLessEqual(abs(ob.disturbance), ob.c.disturbance_limit_mps2)

    def test_config(self):
        self.assertEqual(Config().joint_observer_enabled, 0)
        for args in ({'joint_observer_enabled': 2}, {'joint_observer_enabled': -1},
                     {'joint_disturbance_process_noise': 0}, {'joint_disturbance_process_noise': -1},
                     {'joint_disturbance_process_noise': float('nan')},
                     {'joint_disturbance_process_noise': float('inf')}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                Config(**args)

    def test_disabled_exact_baseline(self):
        ob = Observer(Config(adaptation_tau_s=.5))
        old = baseline.Observer(baseline.Config(adaptation_tau_s=.5))
        rng = random.Random(10)
        held = [None, None]
        for i in range(6000):
            t = i * .05
            u = .5 * math.sin(i / 220.)
            velocity = 5 + 2 * math.sin(i / 190.)
            for ch in (0, 1):
                if (i + ch) % 2 == 0:
                    value = velocity + rng.gauss(0, .04)
                    if 800 < i < 1000 and ch == 0:
                        value += 5
                    if 2100 < i < 2300:
                        value = 0
                    stamp = t + .1 if 3700 < i < 3800 else t
                    held[ch] = Sample(stamp, value)
            wheels = [None, None] if 1200 < i < 1600 else held
            command = None if 3000 < i < 3100 else Sample(t, u)
            self.assertEqual(asdict(ob.step(t, command, *wheels)), asdict(old.step(t, command, *wheels)))

    def test_original_guard_methods_unchanged(self):
        def methods(path):
            tree = ast.parse(path.read_text())
            cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Observer')
            return {n.name: ast.dump(n, include_attributes=False) for n in cls.body if isinstance(n, ast.FunctionDef)}
        a, b = methods(BASE_PATH), methods(ROOT / 'src/reserve_odometry/reserve_odometry/core.py')
        for name in ('_valid', '_wheel', '_clear_reacquire', '_take_pending_pair', '_reacquire_pair',
                     'drive_target', 'resistance'):
            self.assertEqual(a[name], b[name], name)

    def test_joseph_matches_matrix_form_joint_and_schmidt(self):
        for learn in (False, True):
            ob = self.joint()
            ob.reset(velocity=5)
            ob.pv, ob.pvd, ob.pd = .2, .015, .04
            ob.disturbance = .1
            r, residual = .03, .2
            p = [[ob.pv, ob.pvd], [ob.pvd, ob.pd]]
            k = [ob.pv / (ob.pv + r), ob.pvd / (ob.pv + r) if learn else 0.]
            a = [[1 - k[0], 0], [-k[1], 1]]
            expected = matmul(matmul(a, p), transpose(a))
            expected = [[expected[i][j] + k[i] * r * k[j] for j in range(2)] for i in range(2)]
            ob._joint_correct(residual, r, learn)
            self.assertAlmostEqual(ob.v, 5 + k[0] * residual)
            self.assertAlmostEqual(ob.disturbance, .1 + k[1] * residual)
            self.assertAlmostEqual(ob.pv, expected[0][0])
            self.assertAlmostEqual(ob.pvd, expected[0][1])
            self.assertAlmostEqual(ob.pd, expected[1][1])
            self.psd(ob)

    def test_integrated_process_noise(self):
        ob = self.joint(rolling_force_n=0, quadratic_drag_n_s2_m2=0)
        ob.reset(velocity=5)
        ob.pv, ob.pvd, ob.pd = .2, .01, .04
        dt, q = .05, ob.c.joint_disturbance_process_noise
        actual = ob._joint_predict(dt, False, 0., 0., 0., 5.)
        self.assertAlmostEqual(actual, .2 + 2 * dt * .01 + dt * dt * .04 + .1 * dt + q * dt ** 3 / 3)
        self.assertAlmostEqual(ob.pvd, .01 + dt * .04 + q * dt * dt / 2)
        self.assertAlmostEqual(ob.pd, .04 + q * dt)
        self.psd(ob)

    def test_motion_jacobian_finite_difference(self):
        for velocity, u in ((12., .8), (-12., .8), (.3, -.8), (5., 0.)):
            ob = self.joint()
            ob.reset(velocity=velocity)
            dt = .05
            alpha = 1 - math.exp(-dt / ob.c.actuator_tau_s)
            def model(v):
                return v + dt * (alpha * ob.drive_target(u, v) - ob.resistance(v))
            eps = 1e-5
            f = (model(velocity + eps) - model(velocity - eps)) / (2 * eps)
            ob.pv, ob.pvd, ob.pd = .2, .01, .04
            q = ob.c.joint_disturbance_process_noise
            expected = f*f*.2 + 2*f*dt*.01 + dt*dt*.04 + ob.c.process_noise_v*dt + q*dt**3/3
            ob._joint_predict(dt, False, u, alpha, (model(velocity)-velocity)/dt, model(velocity))
            self.assertAlmostEqual(ob.pv, expected, places=9)

    def test_covariance_cap_is_psd(self):
        ob = self.joint()
        ob.pv, ob.pvd, ob.pd = 1e8, 1e6, 1e5
        ob._joint_bound_covariance()
        self.psd(ob)
        self.assertLessEqual(ob.pv, ob.c.max_speed_mps ** 2)
        self.assertLessEqual(ob.pd, ob.c.disturbance_limit_mps2 ** 2)

    def test_learning_predicates(self):
        ob = self.joint()
        ob.adapt_previous = Sample(1., 5.)
        samples = [Sample(1.1, 5.02)] * 2
        self.assertTrue(ob._joint_can_learn(samples, True, False))
        self.assertFalse(ob._joint_can_learn(samples, False, False))
        self.assertFalse(ob._joint_can_learn(samples, True, True))
        for t, value in ((1.01, 5.), (1.5, 5.), (1.1, 0.), (1.1, 7.)):
            self.assertFalse(ob._joint_can_learn([Sample(t, value)]*2, True, False))
        ob.adapt_previous = None
        self.assertFalse(ob._joint_can_learn(samples, True, False))

    def test_single_wheel_does_not_learn(self):
        ob = self.joint()
        ob.reset(velocity=5)
        ob.disturbance = .1
        for i in range(40):
            t = i * .05
            ob.step(t, Sample(t, 0), Sample(t, 5), None)
            self.assertEqual(ob.disturbance, .1)
            self.psd(ob)

    def test_stale_command_does_not_learn(self):
        ob = self.joint()
        ob.reset(velocity=5)
        ob.disturbance = .1
        for i in range(40):
            t = i * .05
            ob.step(t, None, Sample(t, 5), Sample(t, 5))
            self.assertEqual(ob.disturbance, .1)

    def test_held_samples_not_reassimilated(self):
        ob = self.joint()
        ob.reset(velocity=5)
        sample = Sample(0, 5)
        ob.step(0, Sample(0, 0), sample, sample)
        ob.disturbance = .1
        e = ob.step(.05, Sample(.05, 0), sample, sample)
        self.assertEqual(e.mode, 'MODEL_ONLY')
        self.assertEqual(ob.disturbance, .1)
        self.assertEqual(e.front_status, 'DUPLICATE_OR_OLD')

    def test_no_future_initialization(self):
        ob = self.joint()
        e = ob.step(0, Sample(.1, 0), Sample(.1, 5), Sample(.1, 5))
        self.assertEqual(e.mode, 'WAITING_FOR_INITIALIZATION')
        self.assertTrue(e.command_stale)

    def test_dropout_holds_disturbance(self):
        ob = self.joint()
        for i in range(200):
            t = i * .05
            ob.step(t, Sample(t, 0), Sample(t, 5), Sample(t, 5))
        self.assertGreater(ob.disturbance, 0)
        before = ob.disturbance
        for i in range(200, 1200):
            t = i * .05
            ob.step(t, Sample(t, 0), None, None)
            self.assertEqual(ob.disturbance, before)
            self.psd(ob)

    def test_zero_lock_not_stop(self):
        ob = self.joint()
        ob.reset(velocity=5)
        for i in range(120):
            t = i * .05
            e = ob.step(t, Sample(t, 0), Sample(t, 0), Sample(t, 0))
            self.assertNotEqual(e.mode, 'STOPPED')
            self.assertEqual(ob.disturbance, 0)

    def test_confirmed_stop_clears_cross_covariance(self):
        ob = self.joint()
        modes = []
        for i in range(30):
            t = i * .05
            e = ob.step(t, Sample(t, 0), Sample(t, 0), Sample(t, 0))
            modes.append(e.mode)
            if e.mode == 'STOPPED':
                self.assertEqual((ob.v, ob.disturbance, ob.pvd), (0., 0., 0.))
        self.assertIn('STOPPED', modes)

    def test_reacquisition_remains_bounded(self):
        ob = self.joint()
        ob.reset(velocity=10)
        modes = []
        for i in range(40):
            t = i * .1
            before = ob.v
            e = ob.step(t, Sample(t, 0), Sample(t, 5), Sample(t, 5))
            modes.append(e.mode)
            if e.mode == 'REACQUIRING':
                self.assertLessEqual(abs(ob.v-before), ob.c.reacquire_step_mps + ob.c.max_accel_mps2*.1 + 1e-9)
                self.assertEqual(ob.pvd, 0)
                self.assertEqual(ob.disturbance, 0)
        self.assertIn('REACQUIRING', modes)

    def test_state_projection_and_reset(self):
        ob = self.joint()
        ob.reset(velocity=5)
        ob.pv, ob.pvd, ob.pd = .2, .15, .2
        ob._joint_correct(100., .01, True)
        # Direct private correction bypasses the wheel range gate; test only d.
        self.assertEqual(ob.disturbance, ob.c.disturbance_limit_mps2)
        self.assertEqual(ob.pvd, 0)
        ob.reset()
        self.assertEqual((ob.pv, ob.pvd, ob.pd), (1., 0., .09))
        self.assertIsNone(ob.adapt_previous)

    def test_zero_disturbance_limit(self):
        ob = self.joint(disturbance_limit_mps2=0)
        for i in range(50):
            t = .05*i
            ob.step(t, Sample(t, .5), Sample(t, 5), Sample(t, 5))
            self.assertEqual((ob.disturbance, ob.pd, ob.pvd), (0., 0., 0.))
            self.psd(ob)

    def test_randomized_psd_and_bounded_memory(self):
        ob = self.joint()
        rng = random.Random(10010)
        ob.reset(velocity=5)
        state_keys = set(vars(ob))
        for i in range(15000):
            t = i*.05
            velocity = 5 + 4*math.sin(t*.04)
            values = [velocity+rng.gauss(0,.08), velocity+rng.gauss(0,.08)]
            if 120 < t % 200 < 180:
                values = [None, None]
            if 80 < t % 200 < 95:
                values = [0., 0.]
            samples = [None if v is None else Sample(t, v) for v in values]
            ob.step(t, Sample(t, .7*math.sin(t*.02)), *samples)
            self.psd(ob)
            self.assertEqual(set(vars(ob)), state_keys)
            for field in ('used', 'raw_previous', 'pair_pending'):
                self.assertEqual(len(getattr(ob, field)), 2)

    def test_time_contract(self):
        ob = self.joint()
        ob.step(0)
        for t in (0, -.1, 1., float('nan')):
            with self.assertRaises(ValueError):
                ob.step(t)


if __name__ == '__main__':
    unittest.main(verbosity=2)
