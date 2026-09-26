from dataclasses import asdict
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runtime as rt
from reserve_odometry.core import Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver
from reserve_odometry.timeline import Timeline


def stream(n=2400):
    held = [None, None]
    for i in range(n):
        t = i * .05
        phase = t % 30
        u = .4 if phase < 10 else (-.15 if phase < 20 else 0.)
        v = 3 + .2 * math.sin(t / 3)
        if i % 2 == 0:
            held = [Sample(t-.025, v), Sample(t-.02, v+.005)]
        f, r = held
        if 4 <= phase < 5: f = Sample(t, 14)
        if 10 <= phase < 13: f = r = None
        if 16 <= phase < 17: f = r = Sample(t, 0)
        if 21 <= phase < 22: f = Sample(t+1, 15)
        if 23 <= phase < 24: r = Sample(t, float('nan'))
        command = None if 26 <= phase < 27 else Sample(t, u)
        yield t, command, f, r


class CandidateTests(unittest.TestCase):
    def test_pinned_sources(self):
        self.assertGreater(len(rt.verify_pins()), 15)

    def test_unknown_profile_rejected(self):
        with self.assertRaises(ValueError): rt.configuration('best')

    def test_exact_two_changes(self):
        b, br = rt.configuration('main'); c, cr = rt.configuration()
        self.assertEqual(br, cr)
        self.assertEqual({k for k in asdict(b) if getattr(b, k) != getattr(c, k)}, set(rt.TRACTION))
        self.assertEqual(c.max_brake_force_n, 45568.80940352644)
        self.assertEqual((c.adaptation_tau_s, c.common_mode_quarantine_s), (.5, 1.5))

    def test_off_entire_state_and_estimate_parity(self):
        c, ro = rt.configuration('main')
        a = GuardedReadoutObserver(c, readout=ro); b = rt.make_observer(enabled=False)
        for args in stream():
            self.assertEqual(a.step(*args), b.step(*args))
            self.assertEqual(vars(a), vars(b))

    def test_same_class_and_bounded_state_shape(self):
        a, b = rt.make_observer(), rt.make_observer(enabled=False)
        self.assertIs(type(a), GuardedReadoutObserver)
        for args in stream(10000):
            a.step(*args); b.step(*args)
            self.assertEqual(set(vars(a)), set(vars(b)))
        for v in vars(a).values():
            if isinstance(v, (list, tuple, dict)): self.assertLessEqual(len(v), 8)

    def test_configurations_are_not_shared(self):
        a = rt.make_observer(); b = rt.make_observer()
        a.c.max_brake_force_n = 1
        self.assertEqual(b.c.max_brake_force_n, 45568.80940352644)

    def test_braking_and_neutral_force_unchanged_at_same_state(self):
        a, b = rt.make_observer(), rt.make_observer(enabled=False)
        for u in (-1., -.6, -.1, -.02, 0.):
            for v in (-15., -1., 0., 1., 5., 20.):
                self.assertEqual(a.drive_target(u, v), b.drive_target(u, v))

    def test_traction_and_power_both_activate(self):
        a, b = rt.make_observer(), rt.make_observer(enabled=False)
        for v in (1., 5., 20.):
            self.assertGreater(a.drive_target(.5, v), b.drive_target(.5, v))
        c, _ = rt.configuration()
        self.assertAlmostEqual(c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m/c.mass_kg, 1.288533445119809)
        self.assertAlmostEqual(c.max_power_w/c.mass_kg, 10.728192862270857)

    def test_enabled_equals_independent_static_configuration(self):
        c, ro = rt.configuration('main')
        c.total_motor_torque_nm = 3149.748421403977; c.max_power_w = 429127.7144908343
        a = GuardedReadoutObserver(c, readout=ro); b = rt.make_observer()
        for args in stream(): self.assertEqual(a.step(*args), b.step(*args))

    def test_published_distance_integral_and_bounds(self):
        a = rt.make_observer(); previous = None
        for args in stream():
            e = a.step(*args)
            self.assertTrue(all(math.isfinite(x) for x in (e.v, e.s, e.a)))
            self.assertLessEqual(abs(e.v), a.c.max_speed_mps)
            if previous is not None:
                self.assertAlmostEqual(e.s-previous.s, .5*(e.v+previous.v)*(e.t-previous.t), places=10)
            previous = e

    def test_reset_returns_same_fresh_state(self):
        a, b = rt.make_observer(), rt.make_observer()
        for args in stream(100): a.step(*args)
        a.reset(velocity=4, position=12); b.reset(velocity=4, position=12)
        self.assertEqual(vars(a), vars(b))

    def test_future_values_do_not_change_current_estimate(self):
        a, b = rt.make_observer(), rt.make_observer()
        for args in stream(100): a.step(*args); b.step(*args)
        for i in range(100, 120):
            t = i*.05
            self.assertEqual(a.step(t, Sample(t, .3), Sample(t+1, 4), Sample(t+1, 4)),
                             b.step(t, Sample(t, .3), Sample(t+1, 35), Sample(t+1, -35)))

    def test_full_yaml_is_exact_factory_configuration(self):
        text = (rt.HERE/'traction_only.yaml').read_text()
        self.assertEqual(text, rt.candidate_yaml())
        c, ro = rt.configuration(); actual = {}; extra = {}
        for line in text.splitlines():
            key, sep, value = line.strip().partition(':')
            if key.startswith('model.'): actual[key[6:]] = float(value)
            elif key.startswith('readout.'): extra[key[8:]] = float(value)
        self.assertEqual(actual, asdict(c)); self.assertEqual(extra, asdict(ro))
        self.assertIn('    alignment_delay_s: 0.0', text)
        self.assertIn('    front_scale: 0.2777777777777778', text)

    def test_controls_are_not_alternative_winners(self):
        manifest = rt.model_manifest()
        self.assertEqual([k for k,v in manifest.items() if v['selectable']], ['candidate'])
        b, _ = rt.configuration('brake_only_control')
        self.assertEqual(b.total_motor_torque_nm, 2905.0616664738573)
        self.assertEqual(b.max_brake_force_n, rt.H44_BRAKE)

    def test_pin_mismatch_fails_closed(self):
        with patch.object(rt.hashlib, 'sha256') as sha:
            sha.return_value.hexdigest.return_value = 'bad'
            with self.assertRaises(ValueError): rt.verify_pins()


if __name__ == '__main__': unittest.main()
