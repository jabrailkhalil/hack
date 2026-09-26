"""Mechanism tests only: these do not prove accuracy on real recordings."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'src/reserve_odometry'), str(ROOT/'tools/research_h09')]
from reserve_odometry.core import Config, Sample
from reserve_odometry.stop_history import StopHistory
from candidate import implementations


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.h = StopHistory()
        self.c = Config()

    def tick(self, t, *, value=0., wheels=None, statuses=('ACCEPTED','ACCEPTED'),
             u=0., predicted=0., stale=False):
        return self.h.update(t=t, u=u, predicted=predicted, command_stale=stale,
                             wheels=wheels if wheels is not None else (Sample(t,value),Sample(t,value)),
                             statuses=statuses, config=self.c)

    def latch(self):
        self.assertFalse(self.tick(0.))
        self.assertFalse(self.tick(.1))
        self.assertTrue(self.tick(.2))

    def test_three_pairs_and_duration_required(self):
        for t in (0., .05, .1, .15): self.assertFalse(self.tick(t))
        self.assertTrue(self.tick(.2))

    def test_held_samples_are_not_votes(self):
        wheels = (Sample(0.,0.), Sample(0.,0.))
        self.assertFalse(self.tick(0., wheels=wheels))
        for t in (.05,.1,.15,.2):
            self.assertFalse(self.tick(t,wheels=wheels,statuses=('DUPLICATE_OR_OLD',)*2))
        self.assertEqual(self.h.count,1)

    def test_one_channel_cannot_supply_both_votes(self):
        self.tick(0.)
        for t in (.05,.1,.15,.2):
            self.assertFalse(self.tick(t,wheels=(Sample(t,0.),Sample(0.,0.)),
                                      statuses=('ACCEPTED','DUPLICATE_OR_OLD')))

    def test_alternating_channels_confirm(self):
        f,r=Sample(0.,0.),Sample(0.,0.)
        self.tick(0.,wheels=(f,r),statuses=('ACCEPTED','DUPLICATE_OR_OLD'))
        for t in (.05,.15,.25):
            r=Sample(t,0.)
            result=self.tick(t,wheels=(f,r),statuses=('DUPLICATE_OR_OLD','ACCEPTED'))
            if t < .25: self.assertFalse(result)
            else: self.assertTrue(result)
            f=Sample(t+.05,0.)
            self.tick(t+.05,wheels=(f,r),statuses=('ACCEPTED','DUPLICATE_OR_OLD'))

    def test_hysteresis(self):
        self.assertFalse(self.tick(0.,value=.03))
        self.latch()
        self.assertTrue(self.tick(.3,value=.04))
        self.assertFalse(self.tick(.4,value=.05))

    def test_slow_creep_cannot_enter(self):
        for t in range(30): self.assertFalse(self.tick(t*.1,value=.06))

    def test_traction_releases_immediately(self):
        self.latch(); self.assertFalse(self.tick(.25,u=.05))

    def test_stale_command_releases_immediately(self):
        self.latch(); self.assertFalse(self.tick(.25,stale=True))

    def test_missing_stale_future_inputs_release(self):
        for wheels in ((None,Sample(.3,0.)),(Sample(0.,0.),Sample(.3,0.)),
                       (Sample(.4,0.),Sample(.3,0.))):
            self.h.reset(); self.latch()
            self.assertFalse(self.tick(.3,wheels=wheels))

    def test_rejected_wheel_releases(self):
        for status in ('RATE_ANOMALY','MODEL_DISAGREEMENT','RANGE','REACQUIRE_ACCEPTED'):
            self.h.reset(); self.latch()
            self.assertFalse(self.tick(.3,statuses=(status,'ACCEPTED')))

    def test_skew_releases(self):
        self.latch()
        self.assertFalse(self.tick(.4,wheels=(Sample(.4,0.),Sample(.25,0.))))

    def test_model_guard_never_relaxed(self):
        self.latch(); self.assertFalse(self.tick(.3,predicted=.25))
        for i in range(30): self.assertFalse(self.tick(1+i*.1,predicted=3.))

    def test_stricter_entry_model_guard(self):
        for i in range(30): self.assertFalse(self.tick(i*.1,predicted=.10))

    def test_changed_duplicate_is_not_trusted(self):
        self.latch()
        self.assertFalse(self.tick(.25,wheels=(Sample(.2,.01),Sample(.2,0.)),
                                  statuses=('DUPLICATE_OR_OLD',)*2))

    def test_expired_confirmation_restarts(self):
        self.tick(0.); self.tick(.1)
        self.assertFalse(self.tick(.4)); self.assertEqual(self.h.count,1)

    def test_reset_drops_history(self):
        self.latch(); self.h.reset()
        self.assertFalse(self.h.stopped); self.assertEqual(self.h.count,0)
        self.assertEqual(self.h.trusted,[None,None])

    def test_memory_is_bounded(self):
        for i in range(10000): self.tick(i*.1)
        self.assertEqual(len(self.h.trusted),2); self.assertEqual(len(self.h.consumed),2)
        self.assertLessEqual(self.h.count,3); self.assertFalse(hasattr(self.h,'__dict__'))


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # In a checkout, candidate loader uses git show at the exact baseline.
        import os
        cls.base,cls.candidate,_=implementations(os.environ.get('H09_BASELINE_ROOT'))
        cls.parameters=json.loads((ROOT/'src/reserve_odometry/config/adaptive_v5.json').read_text())['config']

    def test_stop_and_immediate_launch(self):
        o=self.candidate.Observer(self.candidate.Config(**self.parameters))
        for i in range(21):
            t=i*.05; e=o.step(t,Sample(t,0.),Sample(t,0.),Sample(t,0.))
        self.assertEqual(e.mode,'STOPPED')
        e=o.step(1.05,Sample(1.05,1.),Sample(1.05,0.),Sample(1.05,0.))
        self.assertNotEqual(e.mode,'STOPPED'); self.assertGreater(e.v,0.)
        o.reset(); self.assertEqual(o.stop_history.count,0)

    def test_no_stop_with_locked_wheels_at_model_speed(self):
        o=self.candidate.Observer(self.candidate.Config(**self.parameters)); o.reset(velocity=10.)
        for i in range(61):
            t=i*.05; e=o.step(t,Sample(t,0.),Sample(t,0.),Sample(t,0.))
            self.assertNotEqual(e.mode,'STOPPED')

    def test_future_inputs_do_not_change_estimate(self):
        a=self.candidate.Observer(); b=self.candidate.Observer()
        a.reset(velocity=.01); b.reset(velocity=.01)
        for i in range(11):
            t=i*.05
            x=a.step(t,Sample(t,0.),Sample(t+1.,0.),Sample(t+1.,0.))
            y=b.step(t,Sample(t,0.),None,None)
            self.assertEqual(x,y)


if __name__=='__main__': unittest.main()
