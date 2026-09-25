"""Mechanism checks only; these are not real-recording accuracy evidence."""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from dataclasses import asdict, replace

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'src/reserve_odometry'), str(ROOT / 'tests')]
from reserve_odometry.adaptation import AdaptationSchedule
from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.timeline import Timeline
import test_core

PROFILE = json.loads((ROOT / 'research/H04/config.json').read_text())['config']


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.s = AdaptationSchedule()
        self.c = Config(**PROFILE)

    def tick(self, t, u=.5, **overrides):
        args = dict(t=t, u=u, command_stale=False, mode='FUSED',
                    statuses=['ACCEPTED', 'ACCEPTED'], front=Sample(t, 5.),
                    rear=Sample(t, 5.), predicted=5., config=self.c)
        args.update(overrides)
        return self.s.select(**args)

    def test_first_regime_is_not_transition(self):
        for i in range(10):
            self.assertEqual(self.tick(i*.1), .5)

    def test_traction_coast_brake_and_expiry(self):
        self.tick(0.)
        self.tick(.2)
        self.assertEqual(self.tick(.3, 0.), .25)
        self.assertEqual(self.tick(.6, -.5), .25)
        self.assertEqual(self.tick(1.36, -.5), .5)

    def test_fast_requires_two_tenths_of_trust(self):
        self.tick(0.)
        self.assertEqual(self.tick(.1, 0.), .5)
        self.assertEqual(self.tick(.2, 0.), .25)

    def test_quality_dimensions_each_select_slow(self):
        variants = [dict(front=Sample(-.11, 5.)),
                    dict(front=Sample(-.06, 5.)),
                    dict(front=Sample(0., 5.16)),
                    dict(predicted=5.31),
                    dict(front=Sample(.01, 5.))]
        for v in variants:
            with self.subTest(v=v):
                self.s = AdaptationSchedule()
                self.assertEqual(self.tick(0., **v), 2.)

    def test_exact_quality_boundaries_are_accepted(self):
        self.assertEqual(self.tick(.1, front=Sample(0., 5.),
                                   rear=Sample(.05, 5.15), predicted=5.075), .5)

    def test_fault_blocks_fast_learning_after_return(self):
        self.tick(0.)
        self.tick(.2, 0.)
        self.assertEqual(self.tick(.3, statuses=['RATE_ANOMALY', 'ACCEPTED']), 2.)
        self.assertEqual(self.tick(.4, -.5), 2.)
        self.assertEqual(self.tick(.6, -.5), 2.)
        self.assertEqual(self.tick(.8, -.5), .25)

    def test_all_detected_fault_statuses_reset_trust(self):
        for status in ('MISSING_OR_STALE', 'RANGE', 'RATE_ANOMALY',
                       'MODEL_DISAGREEMENT', 'AMBIGUOUS_PAIR', 'REACQUIRE_ACCEPTED'):
            with self.subTest(status=status):
                self.tick(0.)
                self.assertEqual(self.tick(.1, statuses=[status, 'ACCEPTED']), 2.)
                self.assertIsNone(self.s.trusted_since)

    def test_stale_command_forgets_regime(self):
        self.tick(0.)
        self.tick(.2, 0.)
        self.assertEqual(self.tick(.3, command_stale=True), 2.)
        self.assertIsNone(self.s.regime)
        self.assertEqual(self.tick(.4, -.5), 2.)
        self.assertEqual(self.tick(.9, -.5), .5)

    def test_duplicate_ticks_do_not_extend_window_or_destroy_trust(self):
        self.tick(0.)
        self.tick(.2, 0.)
        until = self.s.fast_until
        self.tick(.25, 0., mode='MODEL_ONLY', statuses=['DUPLICATE_OR_OLD']*2)
        self.assertEqual(self.s.trusted_since, 0.)
        self.assertEqual(self.s.fast_until, until)
        self.assertEqual(self.tick(.3, 0.), .25)

    def test_fixed_size_state_and_gain_bounds(self):
        self.assertFalse(hasattr(self.s, '__dict__'))
        self.assertEqual(len(self.s.__slots__), 4)
        for i in range(1000):
            tau = self.tick(i*.05, (1, 0, -1)[i % 3])
            self.assertIn(tau, (.25, .5, 2.))
            self.assertTrue(0. < 1. - math.exp(-.1/tau) < 1.)


class IntegrationTests(unittest.TestCase):
    def test_invalid_enable_flag(self):
        for value in (-1., .5, 2., float('nan')):
            with self.assertRaises(ValueError):
                Config(adaptation_schedule_enabled=value)

    def test_reset_discards_scheduler_history(self):
        o = Observer(Config(**PROFILE))
        o.adaptation_schedule.regime = 1
        o.adaptation_schedule.fast_until = 100.
        o.reset()
        self.assertEqual(o.adaptation_schedule, AdaptationSchedule())
        self.assertEqual(o.adaptation_tau, .5)

    def test_detected_dropout_holds_disturbance_no_decay(self):
        o = Observer(Config(**PROFILE))
        for i in range(21):
            t = i*.1
            o.step(t, Sample(t, .5), Sample(t, 5.), Sample(t, 5.))
        held = o.disturbance
        self.assertNotEqual(held, 0.)
        for i in range(21, 31):
            t = i*.1
            o.step(t, Sample(t, .5), None, None)
            self.assertEqual(o.disturbance, held)
        self.assertIsNone(o.adapt_previous)

    def test_duplicate_pair_does_not_learn_twice(self):
        o = Observer(Config(**PROFILE))
        for i in range(10):
            t = i*.1
            o.step(t, Sample(t, .5), Sample(t, 5.), Sample(t, 5.))
            held = o.disturbance
            o.step(t+.05, Sample(t+.05, .5), Sample(t, 5.), Sample(t, 5.))
            self.assertEqual(o.disturbance, held)

    def test_schedule_really_changes_algorithm(self):
        base = Observer(Config(**(PROFILE | {'adaptation_schedule_enabled': 0.})))
        candidate = Observer(Config(**PROFILE))
        different = False
        for i in range(101):
            t=i*.05; u=.5 if t<1. else (0. if t<2. else -.5)
            args=(t,Sample(t,u),Sample(t,5.),Sample(t,5.))
            a=base.step(*args); b=candidate.step(*args)
            different |= a.disturbance != b.disturbance
        self.assertTrue(different)

    def test_future_mutation_cannot_change_prefix(self):
        def run(change):
            timeline=Timeline(Observer(Config(**PROFILE)),rate_hz=20.,delay_s=0.)
            result=[]
            for i in range(201):
                t=i*.05
                for ch in range(3):
                    v=(.5 if t<1. else 0.) if ch==0 else (10. if change and t>3. else 5.)
                    timeline.ingest(ch,Sample(t,v))
                    result.extend(e for e,_ in timeline.advance() if e.t<=3.)
            return result
        self.assertEqual(run(False),run(True))

    def test_disabled_path_exactly_matches_pinned_original_core(self):
        path=os.environ.get('H04_BASELINE_CORE')
        if not path:
            self.fail('Set H04_BASELINE_CORE to the pinned original core for an exact A/B check')
        raw=Path(path).read_bytes()
        blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        self.assertEqual(blob,'f6fc8ecd0b4e16018d814407b1944ce26ea550b0')
        spec=importlib.util.spec_from_file_location('h04_original_core',path)
        original=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=original
        spec.loader.exec_module(original)
        old_config=dict(PROFILE);old_config.pop('adaptation_schedule_enabled')
        a=original.Observer(original.Config(**old_config))
        b=Observer(Config(**(old_config|{'adaptation_schedule_enabled':0.})))
        for i in range(1001):
            t=i*.05;u=(.5,0.,-.5)[(i//100)%3]
            wheels=(5.+.1*math.sin(i*.01),5.+.1*math.sin(i*.01))
            if 300<=i<350:wheels=(None,None)
            if 600<=i<620:wheels=(15.,wheels[1])
            def args(S):
                return (t,S(t,u),*(None if v is None else S(t,v) for v in wheels))
            self.assertEqual(asdict(a.step(*args(original.Sample))),asdict(b.step(*args(Sample))))


class CandidateCoreTests(test_core.ObserverTests):
    """Run all existing core scenarios with opt-in H04, including explicit configs."""
    def setUp(self):
        def candidate(config=None):
            c=Config(**PROFILE) if config is None else replace(config,adaptation_schedule_enabled=1.)
            return Observer(c)
        p=patch.object(test_core,'Observer',candidate);p.start();self.addCleanup(p.stop)


if __name__=='__main__':
    unittest.main()
