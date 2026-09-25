"""H07 mechanism tests; synthetic checks are NOT real-bag accuracy evidence."""
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


def original_core():
    if os.environ.get('H07_BASE_CORE'):
        source = Path(os.environ['H07_BASE_CORE']).read_bytes()
    else:
        source = subprocess.check_output(['git', 'show', BASELINE + ':' + CORE])
    blob = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
    if blob != 'f6fc8ecd0b4e16018d814407b1944ce26ea550b0':
        raise AssertionError('The baseline core is not the pinned Git blob')
    module = types.ModuleType('h07_original_core')
    sys.modules[module.__name__] = module
    exec(compile(source, '<pinned-baseline-core>', 'exec'), module.__dict__)
    return module


class ActuatorTests(unittest.TestCase):
    def test_parameters_reject_negative_and_nonfinite(self):
        for key in ('traction_tau_s', 'braking_tau_s'):
            for value in (-1., float('nan'), float('inf'), -float('inf')):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    Config(**{key: value})
        Config(traction_tau_s=0., braking_tau_s=0.)

    def test_selection_and_deadband_boundaries(self):
        o = Observer(Config(actuator_tau_s=.4, traction_tau_s=.2, braking_tau_s=.8))
        for u, tau in [(1., .2), (-1., .8), (.04, .4), (-.04, .4), (0., .4)]:
            self.assertEqual(o.actuator_tau(u), tau)

    def test_independent_fallback(self):
        o = Observer(Config(actuator_tau_s=.4, traction_tau_s=.2))
        self.assertEqual(o.actuator_tau(-.5), .4)
        o = Observer(Config(actuator_tau_s=.4, braking_tau_s=.8))
        self.assertEqual(o.actuator_tau(.5), .4)

    def test_exact_lag_for_all_command_modes(self):
        for u, tau in [(.5, .2), (-.5, .8), (0., .4)]:
            o = Observer(Config(actuator_tau_s=.4, traction_tau_s=.2, braking_tau_s=.8))
            o.reset(velocity=5.)
            o.step(0., Sample(0., u))
            o.drive_a = .3
            target = o.drive_target(u, o.v)
            expected = .3 + (1 - math.exp(-.1/tau)) * (target-.3)
            o.step(.1, Sample(.1, u))
            self.assertEqual(o.drive_a, expected)

    def test_stale_future_invalid_commands_coast(self):
        for command in (None, Sample(-1., -.5), Sample(.2, -.5), Sample(.1, 2.),
                        Sample(.1, float('nan')), Sample(float('nan'), .5)):
            o = Observer(Config(actuator_tau_s=.4, traction_tau_s=.2, braking_tau_s=.8))
            o.reset(velocity=5.)
            o.step(0.)
            o.drive_a = .3
            result = o.step(.1, command)
            self.assertTrue(result.command_stale)
            self.assertEqual(o.drive_a, .3 + (1-math.exp(-.1/.4)) * (-.3))

    def test_braking_reverse_motion_uses_braking_tau(self):
        o = Observer(Config(actuator_tau_s=.4, traction_tau_s=.2, braking_tau_s=.8,
                            travel_direction=-1.))
        o.reset(velocity=-5.)
        o.step(0., Sample(0., -.5))
        target = o.drive_target(-.5, o.v)
        o.step(.1, Sample(.1, -.5))
        self.assertGreater(target, 0.)
        self.assertEqual(o.drive_a, (1-math.exp(-.1/.8))*target)

    def test_switch_preserves_drive_state(self):
        o = Observer(Config(traction_tau_s=.2, braking_tau_s=.8))
        o.reset(velocity=5.)
        o.step(0., Sample(0., .7))
        o.step(.1, Sample(.1, .7))
        old, target = o.drive_a, o.drive_target(-.7, o.v)
        o.step(.2, Sample(.2, -.7))
        self.assertEqual(o.drive_a, old + (1-math.exp(-.1/.8))*(target-old))

    def test_disabled_matches_actual_pinned_core_bit_for_bit(self):
        old = original_core()
        rng = random.Random(7)
        for settings in ({}, {'actuator_tau_s': .3927619145850434, 'adaptation_tau_s': .5}):
            a, b = old.Observer(old.Config(**settings)), Observer(Config(**settings))
            for i in range(3000):
                t = i*.05
                u = [.6, 0., -.5][(i//47) % 3]
                velocity = 5. + .3*math.sin(t*.3)
                command = None if i % 113 == 0 else (t, u)
                front = None if 300 <= i % 700 < 390 else (t, velocity+rng.uniform(-.03, .03))
                rear = None if 300 <= i % 700 < 390 else (t, velocity+rng.uniform(-.03, .03))
                if i % 53 == 0:
                    front = (t+.1, 0.)  # explicitly future, must be ignored
                args_a = [old.Sample(*x) if x else None for x in (command, front, rear)]
                args_b = [Sample(*x) if x else None for x in (command, front, rear)]
                self.assertEqual(asdict(a.step(t, *args_a)), asdict(b.step(t, *args_b)))
                self.assertEqual(a.drive_a, b.drive_a)

    def test_zero_lock_does_not_become_stop(self):
        for traction, braking in [(a*.3927619145850434, b*.3927619145850434)
                                  for a,b in [(.5,1),(1,.5),(2,1),(1,2),(.5,2),(2,.5)]]:
            o = Observer(Config(traction_tau_s=traction, braking_tau_s=braking))
            o.step(0., Sample(0., 0.), Sample(0., 5.), Sample(0., 5.))
            for i in range(1, 41):
                t = i*.05
                e = o.step(t, Sample(t, 0.), Sample(t, 0.), Sample(t, 0.))
                self.assertNotEqual(e.mode, 'STOPPED')
                self.assertGreater(e.v, 1.)

    def test_no_new_history_state(self):
        a, b = Observer(), Observer(Config(traction_tau_s=.2, braking_tau_s=.8))
        self.assertEqual(set(vars(a)), set(vars(b)))
        b.reset(velocity=5.)
        for i in range(4000):
            t = i*.05
            b.step(t, Sample(t, .5 if i % 40 < 20 else -.5))
        self.assertEqual(set(vars(a)), set(vars(b)))
        for name in ('used', 'raw_previous', 'pair_pending'):
            self.assertEqual(len(getattr(b, name)), 2)
        b.reset()
        self.assertEqual(b.drive_a, 0.)


if __name__ == '__main__':
    unittest.main()
