"""Tests of the prerequisite, not evidence of real-record accuracy."""
import importlib.util
import math
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import prerequisite as h
from reserve_odometry.core import Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver


class PrerequisiteTests(unittest.TestCase):
    def test_all_profile_fields_and_v8(self):
        c, r = h.profile()
        self.assertEqual(c.common_mode_quarantine_s, 1.5)
        self.assertEqual(r.gain, 1.)
        self.assertEqual(c.adaptation_tau_s, .5)

    def test_pinned_baseline(self):
        h.verify_sources()

    def test_ratio_both_signs(self):
        for sign in (1, -1):
            for delta in (-.01, -.002, 0, .004, .01):
                f, r = sign * 7 * math.exp(-delta), sign * 7 * math.exp(delta)
                self.assertAlmostEqual(h.ratio_delta(f, r), delta, places=14)
                self.assertAlmostEqual(f * math.exp(delta), r * math.exp(-delta), places=13)

    def test_common_scale_is_not_identifiable(self):
        self.assertEqual(h.ratio_delta(5, 5), h.ratio_delta(5.5, 5.5))
        self.assertNotEqual(5, 5.5)

    def test_multiplicative_slip_is_indistinguishable(self):
        # A persistent opposite slip has the same ratio as scale mismatch.
        expected = .005
        self.assertAlmostEqual(h.ratio_delta(10*math.exp(-expected), 10*math.exp(expected)), expected)

    def test_invalid_ratio_rejected(self):
        for f, r in [(0, 1), (1, 0), (-1, 1), (1, math.inf), (math.nan, 1)]:
            with self.assertRaises(ValueError):
                h.ratio_delta(f, r)

    def test_geometric_mean_and_arithmetic_counterexample(self):
        for delta in (-.01, .01):
            c0 = 1/3.6
            self.assertAlmostEqual(c0*math.exp(delta)*c0*math.exp(-delta), c0*c0)
            self.assertGreater((math.exp(delta)+math.exp(-delta))/2, 1)

    def test_async_ratio_has_bias(self):
        a, skew, speed = .1, .02, 5
        self.assertAlmostEqual(h.ratio_delta(speed, speed+a*skew), a*skew/(2*speed), delta=1e-7)

    def simulate(self, *, front=5., rear=5., skew=0., ticks=60, future=False):
        c, r = h.profile(); probe = h.Probe(c, readout=r); base = GuardedReadoutObserver(c, readout=r)
        f = b = None
        for i in range(ticks):
            t = i*.05
            if i % 2 == 0:
                f = Sample(t + (.1 if future else 0), front)
                b = Sample(t-skew, rear)
            command = Sample(t, 0.)
            e = probe.step(t, command, f, b); ref = base.step(t, command, f, b)
            self.assertEqual(e, ref)
            for key, value in vars(base).items():
                self.assertEqual(value, getattr(probe, key))
        return probe

    def test_collector_exact_full_state_and_outputs(self):
        p = self.simulate()
        self.assertGreater(len(p.pairs), 5)
        self.assertTrue(all(row[1] == 0 for row in p.pairs))

    def test_deduplication(self):
        p = self.simulate()
        self.assertLess(len(p.pairs), 30)
        self.assertEqual(len({row[0] for row in p.pairs}), len(p.pairs))

    def test_near_zero_excluded(self):
        self.assertEqual(len(self.simulate(front=.5, rear=.5).pairs), 0)

    def test_large_skew_excluded(self):
        self.assertEqual(len(self.simulate(skew=.03).pairs), 0)

    def test_future_samples_causal(self):
        self.assertEqual(len(self.simulate(future=True).pairs), 0)

    def test_reset_collector(self):
        p = self.simulate(); p.reset()
        self.assertFalse(p.pairs)
        self.assertIsNone(p.prior_pair)
        self.assertIsNone(p.t)

    def test_prefix_equivalence(self):
        p = self.simulate(ticks=40)
        q = self.simulate(ticks=60)
        self.assertEqual(p.pairs, [x for x in q.pairs if x[0] < 2.])

    def fake_data(self, value=.003):
        records, arrays = [], {}
        groups = [f'{i:02}' for i in range(12)]
        for group in groups:
            bag = 'b' + group
            a = h.np.zeros((600, len(h.COLS)))
            a[:, 1] = value; a[:, 2] = h.np.tile([3,7,15],200)
            a[:, 3] = h.np.repeat([-1,0,1],200); a[:, 4] = 1
            arrays[bag] = a
            records.append(dict(bag=bag, group=group, representative=True))
        return records, arrays, groups

    def test_admission_for_ideal_relative_defect(self):
        result = h.evaluate_premise(*self.fake_data())
        self.assertEqual(result['scientific_verdict'], 'PREREQUISITE_PASS', result['reasons'])
        self.assertEqual(result['delta'], .003)
        self.assertFalse(result['accuracy_contract_passed'])

    def test_zero_defect_inconclusive(self):
        result = h.evaluate_premise(*self.fake_data(0.))
        self.assertEqual(result['scientific_verdict'], 'INCONCLUSIVE')
        self.assertIn('NO_RESOLVED_RELATIVE_MISMATCH', result['reasons'])

    def test_opposite_groups_inconclusive(self):
        records, arrays, groups = self.fake_data()
        for i, a in enumerate(arrays.values()):
            if i % 2 == 0: a[:, 1] *= -1
        result = h.evaluate_premise(records, arrays, groups)
        self.assertEqual(result['scientific_verdict'], 'INCONCLUSIVE')
        self.assertTrue(any('GROUP_UNSTABLE' in x for x in result['reasons']))

    def test_cap_not_relaxed(self):
        result = h.evaluate_premise(*self.fake_data(.03))
        self.assertEqual(result['scientific_verdict'], 'REJECTED')
        self.assertEqual(result['delta'], .01)

    def test_duplicate_bags_do_not_refit(self):
        records, arrays, groups = self.fake_data()
        for i in range(10):
            records.append(dict(bag='dup'+str(i), group='00', representative=False))
            arrays['dup'+str(i)] = arrays['b00'] * 1
            arrays['dup'+str(i)][:,1] = -.008
        result = h.evaluate_premise(records, arrays, groups)
        self.assertEqual(result['delta'], .003)


if __name__ == '__main__':
    unittest.main()
