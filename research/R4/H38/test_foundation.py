"""Tests of the passive diagnostic and scalar mathematics, NOT enabled H38."""
import ast
from dataclasses import asdict
import inspect
import math
from pathlib import Path
import random
import unittest
from unittest.mock import patch

from foundation import Probe, stats
from scalar_rule import student_variance
from support import ROOT, RoleStore, ev, np, profile, Config, Sample, baseline, GuardedReadoutObserver, ReadoutConfig


class ScalarTests(unittest.TestCase):
    def test_scale_is_not_variance(self):
        for nu in (4, 8):
            for r0 in (.01, .04):
                scale = r0 * (nu - 2) / nu
                self.assertNotEqual(scale, r0)
                self.assertAlmostEqual(scale * nu / (nu - 2), r0)

    def test_three_iterations_same_original_prior(self):
        p, r0, residual = .017, .04, 1.1
        for nu in (4, 8):
            error, cov = residual, p
            for _ in range(3):
                r = max(r0, min(100*r0, ((nu-2)*r0+error**2+cov)/(nu+1)))
                k = p/(p+r)
                error = (1-k)*residual
                cov = (1-k)**2*p + k*k*r
            self.assertEqual(student_variance(p, r0, residual, nu), (r, k, cov, 3))
        tree = ast.parse(inspect.getsource(student_variance))
        loops = [x for x in ast.walk(tree) if isinstance(x, ast.For)]
        self.assertEqual(len(loops), 1)
        self.assertEqual(ast.unparse(loops[0].iter), 'range(3)')
        self.assertFalse(any(isinstance(x, ast.While) for x in ast.walk(tree)))

    def test_finite_bounds_joseph_and_reconstructed_gain(self):
        for nu in (4, 8):
            for p in (.000001, .005, .01, .1, 1., 10.):
                for r0 in (.01, .04):
                    for residual in (0., .01, .3, .8, 2., 100.):
                        r, k, cov, iterations = student_variance(p, r0, residual, nu)
                        self.assertTrue(all(map(math.isfinite, (r,k,cov))))
                        self.assertLessEqual(r0, r)
                        self.assertLessEqual(r, 100*r0)
                        self.assertTrue(0 < k < 1 and 0 < cov <= p)
                        self.assertAlmostEqual(cov, p*r/(p+r), places=12)
                        self.assertAlmostEqual(1-cov/p, k, places=12)
                        self.assertEqual(iterations, 3)

    def test_posterior_floor_is_a_distinct_caveat(self):
        r, k, cov, _ = student_variance(1e-10, .01, 0., 4)
        floored = max(1e-8, cov)
        self.assertGreater(floored, cov)
        self.assertNotAlmostEqual(1-floored/1e-10, k)

    def test_even_in_residual_and_both_confidence_floors(self):
        for nu in (4, 8):
            for r0 in (.01, .04):
                for residual in (.01, .2, 1., 3.):
                    self.assertEqual(student_variance(.005,r0,residual,nu), student_variance(.005,r0,-residual,nu))
                    self.assertGreaterEqual(student_variance(.005,r0,residual,nu)[0], r0)

    def test_small_residual_and_gaussian_limit(self):
        for nu in (4, 8):
            self.assertEqual(student_variance(.005,.01,0.,nu)[0], .01)
        # A mathematical limit check, not a third experimental candidate.
        self.assertAlmostEqual(student_variance(.01,.04,2.,1e14)[0], .04, places=11)

    def test_invalid_and_overflow_report_no_update(self):
        for slot in range(4):
            for x in (math.nan, math.inf, -math.inf):
                args=[.01,.04,.1,4];args[slot]=x
                self.assertIsNone(student_variance(*args))
        for args in ((0.,.04,.1,4),(.01,0.,.1,4),(.01,.04,.1,2),(-1.,.04,.1,8)):
            self.assertIsNone(student_variance(*args))
        self.assertIsNone(student_variance(.01,.04,1e308,4))


class ProbeTests(unittest.TestCase):
    def make_pair(self):
        cfg,rd=profile()
        return baseline(), Probe(Config(**cfg),readout=ReadoutConfig(**rd))

    def same(self, reference, probe, args):
        a,b=reference.step(*args),probe.step(*args)
        self.assertEqual(a,b)
        for key,value in vars(reference).items():
            self.assertEqual(value,getattr(probe,key),key)

    def test_exact_baseline_all_fields_12000_steps(self):
        ref,probe=self.make_pair();rng=random.Random(38);front=rear=None
        for i in range(12000):
            t=i*.05
            if i==6000:
                ref.reset();probe.reset();front=rear=None
            u=(.3 if (i//500)%3==0 else -.2 if (i//500)%3==1 else 0.)
            v=4.+.2*math.sin(i*.004)
            if i%2==0:
                front=Sample(t-.01,v+rng.uniform(-.01,.01))
                rear=Sample(t-.012,v+rng.uniform(-.01,.01))
            if i%1100 in range(700,750):
                front=rear=None
            if i%1700 in range(900,925):
                front=rear=Sample(t,0.)
            if i%2300 in range(1400,1420):
                front=rear=Sample(t,v+5.)
            self.same(ref,probe,(t,Sample(t,u),front,rear))
        self.assertEqual(len(vars(probe)), len(vars(ref))+3)

    def test_future_stale_duplicate_prefix_reset(self):
        ref,probe=self.make_pair()
        self.same(ref,probe,(0.,Sample(0.,0.),Sample(0.,4.),Sample(0.,4.)))
        for i in range(1,30):
            t=i*.05
            self.same(ref,probe,(t,Sample(t+1.,.4),Sample(0.,4.),Sample(t+1.,8.)))
        ref.reset(velocity=2.,position=10.)
        probe.reset(velocity=2.,position=10.)
        for key,value in vars(ref).items():self.assertEqual(value,getattr(probe,key))
        self.assertIsNone(probe.record)
        self.assertIsNone(probe._probe_since)

    def test_bad_timestamp_does_not_mutate_state(self):
        ref,probe=self.make_pair()
        probe.step(0.,Sample(0.,0.),Sample(0.,3.),Sample(0.,3.))
        before=vars(probe).copy()
        with self.assertRaises(ValueError):probe.step(0.)
        self.assertEqual(vars(probe),before)

    def test_full_v8_config_no_hidden_defaults(self):
        cfg,rd=profile()
        self.assertEqual(cfg,asdict(Config(**cfg)))
        self.assertEqual(cfg['common_mode_quarantine_s'],1.5)
        self.assertEqual(cfg['wheel_time_compensation'],0.)
        self.assertEqual(cfg['adaptation_tau_s'],.5)
        self.assertEqual(rd,{'gain':1.,'holdoff_s':.5})

    def test_empty_stats_not_zero_error(self):
        self.assertEqual(stats(np.empty((0,12))), {'n':0})


class IsolationTests(unittest.TestCase):
    def test_test_validation_and_mislabel_denied_before_io(self):
        store=RoleStore('/definitely/not/a/dataset')
        cases=[]
        for role in ('test','validation','train','development'):
            bag=next(r['bag'] for r in store.records.values() if r['split']==role)
            cases.extend((bag,p) for p in ('test','validation','train','development') if p!=role or role in ('test','validation'))
        with patch('sqlite3.connect',side_effect=AssertionError('SQLite touched')), patch.object(ev.ex,'digest',side_effect=AssertionError('File touched')):
            for bag,purpose in cases:
                with self.assertRaises(PermissionError):store.load(bag,purpose)

    def test_probe_is_passive_not_enabled_algorithm(self):
        self.assertIs(Probe.drive_target, GuardedReadoutObserver.drive_target)
        self.assertIs(Probe._wheel, GuardedReadoutObserver._wheel)
        self.assertIs(Probe._reacquire_pair, GuardedReadoutObserver._reacquire_pair)
        self.assertNotIn('def _core_step',inspect.getsource(Probe))

if __name__=='__main__':unittest.main()
