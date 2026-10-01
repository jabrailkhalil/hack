"""Mechanism/invariant tests, not proof of real-data efficacy."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'research/H13'),str(ROOT/'src/reserve_odometry')]
from mechanism import NeutralGuard
from factory import candidate, GuardedReadoutObserver
from reserve_odometry.core import Config, Sample
PROFILE=json.loads((ROOT/'src/reserve_odometry/config/champion_v8.json').read_text())['config']


class H13Tests(unittest.TestCase):
    def evidence(self, g, t, z, pred=5, u=0, a=0, statuses=('CANDIDATE','CANDIDATE')):
        return g.update(t,u,False,Sample(t,z),Sample(t,z),statuses,pred,a,Config())

    def test_two_pairs_not_one(self):
        g=NeutralGuard()
        self.assertFalse(self.evidence(g,0,5))
        self.assertFalse(self.evidence(g,.1,5.4))
        self.assertTrue(self.evidence(g,.2,5.8))
        self.assertEqual(g.triggers,1)
        self.assertAlmostEqual(g.blocked_until,1.2)

    def test_held_samples_never_confirm_twice(self):
        g=NeutralGuard();self.evidence(g,0,5);self.evidence(g,.1,5.4)
        for i in range(5):
            g.update(.11+i*.01,0,False,Sample(.1,5.4),Sample(.1,5.4),('DUPLICATE_OR_OLD',)*2,5,0,Config())
        self.assertEqual(g.suspicious_pairs,1);self.assertEqual(g.triggers,0)

    def test_opposite_mismatch_sign_breaks_streak(self):
        g=NeutralGuard();self.evidence(g,0,5);self.evidence(g,.1,5.4)
        self.assertFalse(self.evidence(g,.2,4.6))
        self.assertEqual(g.triggers,0)

    def test_non_neutral_clears_evidence(self):
        g=NeutralGuard();self.evidence(g,0,5);self.evidence(g,.1,5.4)
        self.assertFalse(self.evidence(g,.2,5.8,u=.1));self.assertIsNone(g.previous)

    def test_strict_acceleration_threshold(self):
        g=NeutralGuard();self.evidence(g,0,5)
        self.evidence(g,.1,5.1,pred=4)
        self.assertEqual(g.triggers,0)

    def test_residual_floor_and_model_accel_gate(self):
        for pred,a in [(5.5,0),(5,.6)]:
            g=NeutralGuard();self.evidence(g,0,5,pred,a=a)
            self.evidence(g,.1,5.2,pred,a=a);self.evidence(g,.2,5.4,pred,a=a)
            self.assertEqual(g.triggers,0)

    def test_future_pair_is_rejected(self):
        g=NeutralGuard()
        self.assertFalse(g.update(1,0,False,Sample(2,99),Sample(2,99),('CANDIDATE',)*2,5,0,Config()))
        self.assertEqual(g.pairs,0)

    def test_reset_clears_all_evidence(self):
        o=candidate()(Config(**PROFILE));self.evidence(o._h13,0,5);self.evidence(o._h13,.1,5.4);self.evidence(o._h13,.2,5.8)
        o.reset();self.assertEqual(o._h13.triggers,0);self.assertEqual(o._h13.last_used,(-float('inf'),)*2)

    def test_disabled_exactly_matches_pinned_champion(self):
        a=GuardedReadoutObserver(Config(**PROFILE));b=candidate(False)(Config(**PROFILE))
        for i in range(6000):
            t=i*.05;z=5 if i<100 or i>150 else 9
            f=Sample(t,z);r=Sample(t,z)
            if 200<=i<260:f=r=None
            cmd=Sample(t,.3 if i%600>400 else 0)
            self.assertEqual(asdict(a.step(t,cmd,f,r)),asdict(b.step(t,cmd,f,r)))

    def test_constant_velocity_baseline_exact(self):
        a=GuardedReadoutObserver(Config(**PROFILE));b=candidate()(Config(**PROFILE))
        for i in range(800):
            t=i*.05;s=Sample(t,5);cmd=Sample(t,0)
            self.assertEqual(asdict(a.step(t,cmd,s,s)),asdict(b.step(t,cmd,s,s)))
        self.assertEqual(b._h13.triggers,0)

    def test_single_wheel_fault_fallback_exact(self):
        a=GuardedReadoutObserver(Config(**PROFILE));b=candidate()(Config(**PROFILE))
        for i in range(200):
            t=i*.05;f=Sample(t,10 if i>=20 else 5);r=Sample(t,5);cmd=Sample(t,0)
            self.assertEqual(asdict(a.step(t,cmd,f,r)),asdict(b.step(t,cmd,f,r)))

    def test_state_size_bounded(self):
        g=NeutralGuard();keys=set(vars(g))
        for i in range(10000):self.evidence(g,i*.1,5+(i%3)*.4)
        self.assertEqual(set(vars(g)),keys)
        self.assertLessEqual(len(g.last_used),2)
        self.assertTrue(g.previous is None or len(g.previous)==3)

if __name__=='__main__':unittest.main()
