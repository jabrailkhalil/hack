import copy
from dataclasses import asdict, replace
import math
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import factory as f
S = f.BASE.core.Sample


def stream(n=1000):
    """Causal stress inputs, not independent accuracy evidence."""
    rng = random.Random(20)
    front = rear = None
    for j in range(n):
        t = j * .05
        command = S(t, .5 if j % 500 < 200 else -.5 if j % 500 < 400 else 0)
        speed = 4 + .5 * math.sin(t / 7)
        if j % 2 == 0:
            front = S(t - .02, speed + rng.uniform(-.05, .05))
            rear = S(t - .01, speed + rng.uniform(-.05, .05))
        if 200 < j % 500 < 220:
            front = S(t - .01, 15.)
        if 250 < j % 500 < 265:
            rear = None
        if 300 < j % 500 < 315:
            front = rear = S(t, 0.)
        yield t, command, front, rear


class H20Tests(unittest.TestCase):
    def test_profile_is_v7(self):
        c, r = f.profile()
        self.assertEqual(c['adaptation_tau_s'], .5)
        self.assertEqual(c['wheel_time_compensation'], 0)
        self.assertEqual(r, dict(gain=1., holdoff_s=.5))
        self.assertEqual(f.OPS, dict(rate_hz=20., alignment_delay_s=0.))

    def test_invalid_alpha(self):
        for alpha in (-.01, .5001, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                f.candidate(alpha)

    def test_disabled_full_state_and_return(self):
        a, b = f.baseline(), f.candidate(0)
        for args in stream(4000):
            ea, eb = a.step(*args), b.step(*args)
            self.assertEqual(asdict(ea), asdict(eb))
            f.assert_disabled(a, b)

    def test_reset_clears_evidence(self):
        b = f.candidate(.5)
        for args in stream(100): b.step(*args)
        b.reset(velocity=3, position=7)
        self.assertIsNone(b._h20_since)
        self.assertIsNone(b._h20_diag)
        self.assertEqual(b._h20_confirmed, 0)
        self.assertEqual(b.v, 3)
        self.assertEqual(b.s, 7)

    def mode(self, direction=1, mode=1):
        b = f.candidate(.5)
        b.reset(velocity=direction * 5)
        b.drive_a = direction * mode * .4
        for j in range(12):
            b._h20_context(j * .05, mode * .5, direction * mode * .5,
                           direction * mode * .3, direction * 5., direction * 5., False)
        return b

    def test_confirmation_dwell(self):
        b = f.candidate(.5); b.reset(velocity=5); b.drive_a = .4
        for j in range(10):
            b._h20_context(j*.05, .5, .5, .4, 5, 5, False)
            self.assertEqual(b._h20_confirmed, 0)
        b._h20_context(.5, .5, .5, .4, 5, 5, False)
        self.assertEqual(b._h20_confirmed, 1)

    def test_modes_both_directions(self):
        for direction in (-1, 1):
            for mode in (-1, 1):
                b = self.mode(direction, mode)
                self.assertEqual(b._h20_confirmed, mode)
                self.assertEqual(b._h20_direction, direction)

    def test_model_mismatch_fallback(self):
        b = self.mode(); b._h20_context(.6, .5, .5, -.1, 5, 5, False)
        self.assertEqual(b._h20_confirmed, 0)
        self.assertIsNone(b._h20_since)

    def test_drive_lag_fallback(self):
        b = self.mode(); b.drive_a = -.2
        b._h20_context(.6, .5, .5, .3, 5, 5, False)
        self.assertEqual(b._h20_confirmed, 0)

    def test_coast_fallback(self):
        b = self.mode(); b._h20_context(.6, 0, .5, .3, 5, 5, False)
        self.assertEqual(b._h20_confirmed, 0)

    def test_stale_fallback(self):
        b = self.mode(); b._h20_context(.6, .5, .5, .3, 5, 5, True)
        self.assertEqual(b._h20_confirmed, 0)

    def test_low_speed_and_direction_fallback(self):
        for predicted, old in ((.49, .49), (0, .2), (5, -5)):
            b = self.mode(); b._h20_context(.6, .5, .5, .3, predicted, old, False)
            self.assertEqual(b._h20_confirmed, 0)

    def test_transition_restarts_dwell(self):
        b = self.mode(); b.drive_a = -.4
        b._h20_context(.6, -.5, -.5, -.3, 5, 5, False)
        self.assertEqual(b._h20_confirmed, 0)
        self.assertEqual(b._h20_since, .6)

    def test_exact_symmetric_fallback(self):
        b = f.candidate(.5); b.reset(velocity=5)
        args = ([S(0, 5.3), S(0, 4.9)], [0, 1], True, 5., 5.1, .0123)
        self.assertEqual(b._h20_weight(*args), (5.1, .0123))
        self.assertFalse(b._h20_diag['changed'])

    def test_unpenalized_sign_exact(self):
        b = self.mode()
        self.assertEqual(b._h20_weight([S(0, 4.8)], [0], False, 5, 4.8, .04), (4.8, .04))

    def test_traction_reduces_overspeed_weight(self):
        b = self.mode(); z, r = b._h20_weight([S(0, 5.3), S(0, 5)], [0, 1], True, 5, 5.15, .01)
        self.assertLess(z, 5.15); self.assertGreater(r, .01)

    def test_brake_reduces_underspeed_weight(self):
        b = self.mode(mode=-1); z, r = b._h20_weight([S(0, 4.7), S(0, 5)], [0, 1], True, 5, 4.85, .01)
        self.assertGreater(z, 4.85); self.assertGreater(r, .01)

    def test_reverse_signs(self):
        b = self.mode(direction=-1); z, r = b._h20_weight([S(0, -5.3), S(0, -5)], [0, 1], True, -5, -5.15, .01)
        self.assertGreater(z, -5.15); self.assertGreater(r, .01)

    def test_single_wheel_does_not_reduce_r(self):
        b = self.mode()
        z, r = b._h20_weight([S(0, 5.2), None], [0], False, 5, 5.2, .04)
        self.assertAlmostEqual(z, 5.2, places=14); self.assertGreater(r, .04)

    def test_correlated_pair_floor(self):
        b = self.mode()
        for v in (5., 5.1, 5.3, 7.):
            original = .01 * max(1, abs(v-5)/.3)
            z, r = b._h20_weight([S(0, v), S(0, v)], [0, 1], True, 5, v, original)
            self.assertGreaterEqual(r, original)
            self.assertGreaterEqual(r, .01)

    def test_weight_bounds_and_convex_target(self):
        for direction in (-1, 1):
            for mode in (-1, 1):
                b = self.mode(direction, mode)
                for e in (-3., -.3, -1e-10, 0., 1e-10, .3, 3.):
                    samples = [S(0, direction*(5+e)), S(0, direction*5)]
                    z, r = b._h20_weight(samples, [0,1], True, direction*5, sum(s.value for s in samples)*.5, .01)
                    for w in b._h20_diag['weights']:
                        self.assertTrue(2/3 <= w <= 1)
                    self.assertGreaterEqual(z, min(s.value for s in samples)-1e-14)
                    self.assertLessEqual(z, max(s.value for s in samples)+1e-14)

    def test_future_and_nonfinite_wheels_not_weighted(self):
        b = f.candidate(.5); b.reset(velocity=5)
        for j in range(30):
            t = j*.05
            e = b.step(t, S(t,.5), S(t+1,5), S(t,float('nan')))
            self.assertEqual(e.front_status, 'MISSING_OR_STALE')
            self.assertEqual(e.rear_status, 'MISSING_OR_STALE')
            self.assertIsNone(b._h20_diag)

    def test_duplicate_not_reassimilated(self):
        b = f.candidate(.5); b.reset(velocity=5)
        for j in range(40):
            t=j*.05; e=b.step(t,S(t,.5),S(t,5+.02*j),S(t,5+.02*j))
        e = b.step(2., S(2.,.5), S(1.95,5.78),S(1.95,5.78))
        self.assertEqual(e.front_status, 'DUPLICATE_OR_OLD')
        self.assertEqual(e.rear_status, 'DUPLICATE_OR_OLD')
        self.assertIsNone(b._h20_diag)

    def test_common_zero_lock_not_assimilated(self):
        b = f.candidate(.5); b.reset(velocity=1.0)
        for j in range(10):
            t=j*.05; e=b.step(t,S(t,0),S(t,0),S(t,0))
            self.assertEqual(e.front_status, 'ZERO_LOCK_SUSPECT')
            self.assertNotEqual(e.mode,'STOPPED')
            self.assertIsNone(b._h20_diag)

    def test_causal_prefix(self):
        a,b=f.candidate(.25),f.candidate(.25)
        inputs=list(stream(1000)); expected=[]
        for args in inputs: expected.append(asdict(a.step(*args)))
        for j,args in enumerate(inputs[:537]): self.assertEqual(asdict(b.step(*args)),expected[j])
        # Future nonfinite data never touched by prefix execution.

    def test_bounded_state_and_finite(self):
        b=f.candidate(.5); shape=None
        for args in stream(10000):
            e=b.step(*args)
            for key in ('s','v','a','variance_v','variance_s','disturbance'):
                self.assertTrue(math.isfinite(getattr(e,key)))
            keys=set(vars(b))
            if shape is None: shape=keys
            self.assertEqual(keys,shape)
            if b._h20_diag:
                self.assertLessEqual(len(b._h20_diag['innovations']),2)
                self.assertLessEqual(len(b._h20_diag['weights']),2)

    def test_time_errors_preserved(self):
        b=f.candidate(.5); b.step(0)
        for t in (0, -.1, .3, float('nan')):
            with self.assertRaises(ValueError): b.step(t)

    def test_bootstrap_and_recovery_off(self):
        a,b=f.baseline(),f.candidate(0.)
        for j in range(80):
            t=j*.05; s=S(t, 7.)
            args=(t,S(t,0),s if j%2 else None,s if not j%2 else None)
            self.assertEqual(asdict(a.step(*args)),asdict(b.step(*args)))
            f.assert_disabled(a,b)

if __name__ == '__main__': unittest.main()
