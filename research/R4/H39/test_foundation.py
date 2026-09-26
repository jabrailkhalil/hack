import math
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
import foundation as f


class FoundationTests(unittest.TestCase):
    def events(self, wheel):
        return np.array([(t,0,u) for t,u,v in wheel]+[(t,1,v) for t,u,v in wheel],float)[
            np.argsort([t for t,u,v in wheel]*2,kind='stable')]

    def test_timestamp_not_value_defines_new_sample(self):
        a,c=f.collect(self.events([(0,0,1),(.1,0,1),(.2,0,1.1)]))
        self.assertEqual(c[0]['new_stamp'],3)
        self.assertEqual(c[0]['new_stamp_unchanged_value'],1)
        self.assertEqual(len(a[0]),1)

    def test_duplicate_stamp_not_evidence(self):
        a,c=f.collect(self.events([(0,0,1),(.1,0,1.1),(.1,0,1.2)]))
        self.assertEqual(c[0]['duplicate_or_old_stamp'],1)
        self.assertEqual(len(a[0]),1)

    def test_future_command_unavailable(self):
        a,c=f.collect(np.array([[1,0,.5],[0,1,1],[.1,1,1.1]]))
        self.assertEqual(len(a[0]),0)

    def test_stale_command_unavailable(self):
        a,c=f.collect(np.array([[0,0,.5],[1,1,1],[1.1,1,1.1]]))
        self.assertEqual(len(a[0]),0)

    def test_gap_does_not_make_changed_sample(self):
        a,c=f.collect(self.events([(0,0,1),(1,0,1.1)]))
        self.assertEqual(len(a[0]),0)

    def test_near_zero_not_foundation(self):
        a,c=f.collect(self.events([(0,0,0),(.1,0,.01),(.2,0,.02)]))
        self.assertEqual(len(a[0]),0)

    def test_three_regimes(self):
        a,c=f.collect(self.events([(0,0,1),(.1,.5,1.1),(.2,0,1.2),(.3,-.5,1.3)]))
        np.testing.assert_equal(a[0][:,2],[0,1,2])

    def groups(self,q=.05,shift=.013):
        ix=np.tile(np.arange(1100),3)
        regime=np.tile(np.arange(3),1100)
        return {str(i):np.column_stack((np.arange(len(ix))*.1,shift+q*ix,regime)) for i in range(3)}

    def test_true_shifted_grid_refinement(self):
        g=self.groups(); r=f.refine(.05,g)
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r[0],.05,places=12)
        self.assertAlmostEqual(r[1],.013,places=10)
        self.assertTrue(f.evaluate_grid(g,r[0],r[1])['passed'])

    def test_proposals_contain_physical_grid(self):
        p=f.proposals(self.groups())
        self.assertLess(np.min(abs(p-.05)),1e-10)

    def test_fitting_selects_coarsest_not_divisor(self):
        r,a=f.fit_grid(self.groups())
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r[0],.05,places=10)

    def test_changed_offset_fails_check(self):
        g=self.groups();self.assertFalse(f.evaluate_grid(g,.05,.023)['passed'])

    def test_continuous_levels_reject_coarse_grid(self):
        rng=np.random.default_rng(39)
        g=self.groups()
        for a in g.values():a[:,1]=rng.uniform(1,8,len(a))
        self.assertIsNone(f.refine(.05,g))

    def test_fixed_speed_does_not_qualify(self):
        a=np.column_stack((np.arange(3000),np.ones(3000),np.zeros(3000)))
        self.assertFalse(f.qualify(a))

    def test_practical_floor_units(self):
        self.assertAlmostEqual(f.QPRACTICAL**2/(12*.1**2),.01)
        self.assertLess((1e-5)**2/(12*.1**2),.01)

    def test_empty_pair_bound_missing(self):
        self.assertIsNone(f.continuous_pair_bound([])['max_fraction'])

    def test_grid_pair_bound_can_be_one(self):
        b=f.continuous_pair_bound([.05,.1,.15,.05,.2])
        self.assertEqual(b['max_fraction'],1)

    def test_impossible_gap_practical(self):
        self.assertEqual(f.continuous_pair_bound([.002]*100)['max_fraction'],0)

    def test_tiny_gap_can_fit_zero_bin(self):
        self.assertEqual(f.continuous_pair_bound([1e-9]*100)['max_fraction'],1)

    def test_sweep_upper_bounds_dense_grid(self):
        rng=np.random.default_rng(39)
        d=rng.uniform(.001,1,100)
        b=f.continuous_pair_bound(d)
        for q in np.linspace(f.QPRACTICAL,.5,1000):
            frac=np.mean(abs(d-np.rint(d/q)*q)<=.002*q+2e-10)
            self.assertLessEqual(frac,b['max_fraction']+1e-12)

    def test_disjoint_pair_outlier_bound(self):
        d=np.r_[np.full(99,.05),.003]
        self.assertEqual(f.continuous_pair_bound(d)['max_fraction'],.99)

    def test_collection_is_prefix_causal(self):
        a=self.events([(i*.1,0,1+i*.01) for i in range(30)])
        short=f.collect(a[:20])[0][0];full=f.collect(a)[0][0]
        np.testing.assert_array_equal(short,full[:len(short)])

    def test_collect_does_not_mutate_inputs(self):
        a=self.events([(0,0,1),(.1,.3,1.2)]);b=a.copy();f.collect(a)
        np.testing.assert_array_equal(a,b)


if __name__=='__main__':unittest.main()
