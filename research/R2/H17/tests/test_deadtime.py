import copy
from dataclasses import asdict
import json
import math
from pathlib import Path
import random
import unittest
from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.command_deadtime import CommandDeadtimeObserver
from reserve_odometry.timeline import Timeline

ROOT = Path(__file__).resolve().parents[4]
PROFILE = json.loads((ROOT/'src/reserve_odometry/config/guarded_readout_v7.json').read_text())

def cfg():
    return Config(**PROFILE['config'])

def make(delay=.1):
    return CommandDeadtimeObserver(cfg(), delay_s=delay, readout=ReadoutConfig(**PROFILE['readout']))

class DeadtimeTests(unittest.TestCase):
    def test_invalid_delays(self):
        for x in [-.01,.200001,float('nan'),float('inf')]:
            with self.assertRaises(ValueError): make(x)

    def test_fixed_profile(self):
        c=cfg()
        self.assertEqual(c.actuator_tau_s,.3927619145850434)
        self.assertEqual(c.wheel_time_compensation,0)
        self.assertEqual(c.adaptation_tau_s,.5)

    def test_off_exact_estimate_and_all_baseline_state(self):
        a=GuardedReadoutObserver(cfg()); b=make(0); rng=random.Random(17)
        for k in range(3000):
            t=k*.05
            cmd=Sample(t,.3*math.sin(t)) if k%13 else Sample(t-1,.8)
            f=Sample(t,5+.1*math.sin(t)) if k%7 else None
            r=Sample(t,5+.1*math.sin(t)+.01*rng.random()) if k%11 else None
            self.assertEqual(a.step(t,cmd,f,r),b.step(t,cmd,f,r))
            for key,val in vars(a).items(): self.assertEqual(val,getattr(b,key),key)
        self.assertEqual(len(b.command_history),0)
        self.assertEqual(b.delay_changed_ticks,0)

    def test_neutral_before_history(self):
        a=make(.2);a.reset(velocity=4)
        e=a.step(0,Sample(0,1))
        self.assertEqual(a.delayed_command,0)
        self.assertFalse(e.command_stale)
        self.assertEqual(a.delay_status,'NO_HISTORY')

    def test_step_onset_separate_from_tau(self):
        for L in [.05,.1,.2]:
            a=make(L);a.reset(velocity=4)
            for k in range(20):
                t=k*.05;cmd=Sample(t,0 if t<.5 else 1)
                a.step(t,cmd)
                if t<.5+L-1e-9: self.assertEqual(a.drive_a,0)
                if t>.5+L+1e-9: self.assertGreater(a.drive_a,0)
            self.assertEqual(a.c.actuator_tau_s,cfg().actuator_tau_s)

    def test_selected_stamp_not_after_target(self):
        a=make(.2)
        for k in range(200):
            t=k*.05;a.step(t,Sample(t,.3),Sample(t,3),Sample(t,3))
            if a.delayed_stamp is not None:self.assertLessEqual(a.delayed_stamp,t-.2)

    def test_hold_previous_zero_order_command(self):
        a=make(.1);a.reset(velocity=4)
        for t,u in [(0,.2),(.05,.8),(.1,.8)]:a.step(t,Sample(t,u))
        self.assertEqual(a.delayed_command,.2)
        self.assertEqual(a.delayed_stamp,0)

    def test_duplicate_not_added(self):
        a=make(.1);a.reset(velocity=4);s=Sample(0,.3)
        for k in range(6):a.step(k*.05,s)
        self.assertEqual(len(a.command_history),1)
        self.assertEqual(a.delayed_command,.3)

    def test_duplicate_changed_value_not_assimilated(self):
        a=make(.1);a.reset(velocity=4)
        a.step(0,Sample(0,.3));a.step(.1,Sample(0,.9))
        self.assertEqual(a.delayed_command,.3)

    def test_old_stamp_not_poison_history(self):
        a=make(.1);a.reset(velocity=4)
        a.step(0,Sample(0,.3));a.step(.05,Sample(.05,.4));a.step(.1,Sample(.025,.9))
        self.assertEqual(a.command_last_seen,.05)
        self.assertEqual(a.delayed_command,.3)

    def test_current_stale_forces_neutral_without_stamp_refresh(self):
        a=make(.2);a.reset(velocity=4)
        for k in range(12):e=a.step(k*.05,Sample(0,.8))
        self.assertTrue(e.command_stale)
        self.assertEqual(a.delayed_command,0)
        self.assertEqual(a.delay_status,'CURRENT_INVALID')

    def test_fresh_current_cannot_resurrect_stale_predecessor(self):
        a=make(.2);a.reset(velocity=4)
        for k in range(11):a.step(k*.05,Sample(0,.9))
        e=a.step(.55,Sample(.55,.2))
        self.assertFalse(e.command_stale)
        self.assertEqual(a.delayed_command,0)
        self.assertEqual(a.delay_status,'NO_HISTORY')

    def test_future_not_used_or_stored(self):
        a=make(.1);a.reset(velocity=4)
        e=a.step(0,Sample(.01,1))
        self.assertTrue(e.command_stale)
        self.assertFalse(a.command_history)
        self.assertEqual(a.delayed_command,0)

    def test_invalid_command_handling(self):
        for s in [None,Sample(0,2),Sample(0,float('nan')),Sample(float('nan'),.3)]:
            a=make();a.reset(velocity=4);e=a.step(0,s)
            self.assertTrue(e.command_stale);self.assertEqual(a.delayed_command,0)

    def test_time_window_and_count_bound(self):
        a=make(.2);a.reset(velocity=4)
        for k in range(10000):
            t=k*.0005;a.step(t,Sample(t,.3))
            self.assertLessEqual(len(a.command_history),64)
            self.assertLessEqual(sum(s.t<t-.25 for s in a.command_history),1)
        self.assertEqual(a.command_history.maxlen,64)

    def test_reset_clears_every_history(self):
        a=make()
        for k in range(20):a.step(k*.05,Sample(k*.05,.3),Sample(k*.05,3),Sample(k*.05,3))
        a.reset();self.assertEqual(vars(a),vars(make()))

    def test_invalid_time_does_not_mutate(self):
        a=make();a.step(0,Sample(0,.2));before=copy.deepcopy(vars(a))
        for t in [0,-.1,float('nan'),float('inf'),.3]:
            with self.assertRaises(ValueError):a.step(t,Sample(0,.9))
            self.assertEqual(before,vars(a))

    def test_direct_drive_target_unchanged(self):
        a=GuardedReadoutObserver(cfg());b=make(.2)
        for u in [-1,-.1,0,.1,1]:self.assertEqual(a.drive_target(u,4),b.drive_target(u,4))

    def test_prefix_causality(self):
        for L in [.05,.1,.2]:
            a,b=make(L),make(L)
            prefix=[]
            for k in range(100):
                t=k*.05;args=(t,Sample(t,.3),Sample(t,3+.1*t),Sample(t,3+.1*t))
                prefix.append(a.step(*args));self.assertEqual(prefix[-1],b.step(*args))
            previous=copy.deepcopy(prefix)
            for k in range(100,120):
                t=k*.05;a.step(t,Sample(t,-1),Sample(t,0),Sample(t,0))
            self.assertEqual(prefix,previous)
            self.assertNotEqual(a.t,b.t)

    def test_timeline_off_outputs_and_counters(self):
        a,b=Timeline(GuardedReadoutObserver(cfg()),delay_s=0),Timeline(make(0),delay_s=0)
        for k in range(250):
            t=k*.05
            for ch,val in [(0,.3),(1,3),(2,3)]:
                s=Sample(t,val)
                self.assertEqual(a.ingest(ch,s),b.ingest(ch,s))
                self.assertEqual(list(a.advance()),list(b.advance()))
        for key in ['tick_index','dropped','resets','catchup_events']:self.assertEqual(getattr(a,key),getattr(b,key))

    def test_low_speed_lock_protected(self):
        for L in [.05,.1,.2]:
            a=make(L);a.reset(velocity=1.5)
            for k in range(15):
                t=k*.05;e=a.step(t,Sample(t,.3),Sample(t,0),Sample(t,0))
                self.assertNotEqual(e.mode,'STOPPED')
                self.assertGreater(e.v,.25)

    def test_true_stop_retained(self):
        a=make(.2)
        for k in range(25):
            t=k*.05;e=a.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
        self.assertEqual(e.mode,'STOPPED');self.assertEqual(e.v,0)

    def test_no_nonfinite_estimates(self):
        a=make(.2)
        for k in range(1000):
            t=k*.05;e=a.step(t,Sample(t,math.sin(t)),Sample(t,4),Sample(t,4))
            for key in ['t','s','v','a','variance_v','variance_s','disturbance']:self.assertTrue(math.isfinite(getattr(e,key)))

if __name__=='__main__': unittest.main()
