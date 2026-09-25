"""Mechanism and invariance checks, not evidence of real-data accuracy."""
from dataclasses import asdict
import math
from pathlib import Path
import random
import sys
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/research_h19'))
from factory import Factory,Config,plain,equal_baseline,ev
from data import Store
F=Factory()
M=F.candidate['sequential_faults']; Sample=F.candidate['core'].Sample

class Mechanism(unittest.TestCase):
    def setUp(self):
        self.d=M.SequentialEvidence(M.SequentialConfig());self.c=Config()
    def feed(self,k,front=5.2,rear=5.,command_stale=False,accepted=(0,1),statuses=('CANDIDATE','CANDIDATE')):
        t=round(k*.1,8);samples=[Sample(t,front),Sample(t,rear)]
        return self.d.update(t,self.c,samples,statuses,list(accepted),5.,.01,command_stale)
    def test_initial_sample_no_evidence_time(self):
        self.feed(0); self.assertEqual(self.d.positive,[0.,0.])
    def test_positive_single_channel(self):
        for k in range(8):self.feed(k)
        self.assertEqual(self.d.weights,[.25,1.]);self.assertTrue(self.d.suspect[0])
    def test_negative_single_channel(self):
        for k in range(8):self.feed(k,front=4.8)
        self.assertEqual(self.d.weights,[.25,1.]);self.assertGreater(self.d.negative[0],0.)
    def test_rear_attribution(self):
        for k in range(8):self.feed(k,front=5.,rear=5.2)
        self.assertEqual(self.d.weights,[1.,.25])
    def test_common_mode_not_isolated(self):
        for k in range(30):self.feed(k,front=5.2,rear=5.2)
        self.assertEqual(self.d.weights,[1.,1.]);self.assertEqual(self.d.positive,[0.,0.])
    def test_low_speed_inactive(self):
        for k in range(30):self.feed(k,front=.4,rear=.2)
        self.assertEqual(self.d.weights,[1.,1.]);self.assertEqual(self.d.positive,[0.,0.])
    def test_duplicates_not_accumulated(self):
        for k in range(4):self.feed(k)
        before=self.d.positive.copy()
        for _ in range(20):self.feed(3)
        self.assertEqual(before,self.d.positive)
    def test_held_not_new(self):
        self.feed(0);self.feed(1)
        before=self.d.positive.copy()
        self.d.update(.15,self.c,[None,None],['DUPLICATE_OR_OLD']*2,[],5.,.01,False)
        self.assertEqual(before,self.d.positive);self.assertEqual(self.d.new_sample,[False,False])
    def test_stale_clears(self):
        for k in range(8):self.feed(k)
        self.d.update(1.2,self.c,[None,None],['MISSING_OR_STALE']*2,[],5.,.01,False)
        self.assertEqual(self.d.weights,[1.,1.]);self.assertEqual(self.d.positive,[0.,0.])
    def test_hard_rejection_not_evidence(self):
        for k in range(8):self.feed(k,statuses=('RATE_ANOMALY','CANDIDATE'),accepted=(1,))
        self.assertEqual(self.d.weights,[1.,1.]);self.assertEqual(self.d.positive,[0.,0.])
    def test_freshness_gap_resets(self):
        for k in range(8):self.feed(k)
        self.feed(15);self.assertEqual(self.d.positive,[0.,0.])
    def test_stale_command_no_action(self):
        for k in range(8):self.feed(k)
        self.feed(8,command_stale=True);self.assertEqual(self.d.weights,[1.,1.])
    def test_recovery_hysteresis(self):
        for k in range(8):self.feed(k)
        for k in range(8,35):self.feed(k,front=5.,rear=5.)
        self.assertEqual(self.d.suspect,[False,False]);self.assertEqual(self.d.weights,[1.,1.])
    def test_finite_epoch_resets_under_continuous_bias(self):
        for k in range(40):self.feed(k)
        self.assertGreater(self.d.positive[0],.3)
        self.feed(40);self.assertEqual(self.d.positive,[0.,0.]);self.assertEqual(self.d.suspect,[False,False])
    def test_monitor_only_never_weights(self):
        self.d=M.SequentialEvidence(M.SequentialConfig(monitor_only=True))
        for k in range(8):self.feed(k)
        self.assertTrue(self.d.suspect[0]);self.assertEqual(self.d.weights,[1.,1.])
    def test_config_validation(self):
        for v in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):M.SequentialConfig(threshold_s=v)
        with self.assertRaises(ValueError):M.SequentialConfig(threshold_s=3)
        with self.assertRaises(ValueError):M.SequentialConfig(enabled=1)
    def test_state_bounded_in_size_value_and_time(self):
        keys=self.d.__slots__
        for k in range(10000):
            self.feed(k,front=5.2 if k%20 else 4.8)
            self.assertTrue(all(0<=x<=2 for x in self.d.positive+self.d.negative))
            self.assertEqual(keys,self.d.__slots__)
            self.assertTrue(all(x is None or k*.1-x<4.00000001 for x in self.d.epoch))
        self.assertTrue(all(len(getattr(self.d,key))==2 for key in keys if key!='options'))

class Integration(unittest.TestCase):
    def stream(self,count=300):
        rng=random.Random(123)
        for k in range(count):
            t=round(k*.05,8);u=.1 if k%90<30 else -.1
            v=2+.005*k+.01*rng.uniform(-1,1)
            yield t,Sample(t,u),Sample(t,v),Sample(t,v+.015)
    def test_disabled_all_state_exact(self):
        a=F.make('baseline');b=F.make('off');c=F.make('pristine')
        for args in self.stream(600):
            x=a.step(*args);self.assertEqual(plain(x),plain(b.step(*args)));self.assertEqual(plain(x),plain(c.step(*args)))
            equal_baseline(a,b);equal_baseline(a,c)
    def test_monitor_output_and_inner_exact(self):
        a=F.make('baseline');b=F.make('monitor')
        for args in self.stream():
            self.assertEqual(plain(a.step(*args)),plain(b.step(*args)));equal_baseline(a,b)
    def test_prefix_is_causal(self):
        stream=list(self.stream());a=F.make('h03');b=F.make('h03')
        pre=[plain(a.step(*x)) for x in stream[:137]]
        full=[plain(b.step(*x)) for x in stream]
        self.assertEqual(pre,full[:137])
    def test_future_samples_never_contribute(self):
        a=F.make('h03')
        for k in range(30):
            t=k*.05;e=a.step(t,Sample(t,0),Sample(t+1,5),Sample(t+1,5.2))
            self.assertEqual(e.mode,'WAITING_FOR_INITIALIZATION')
            self.assertEqual(a._h19_detector.positive,[0.,0.])
    def test_stop_and_zero_lock_protection(self):
        for name in ('baseline','h03','h06'):
            a=F.make(name);a.reset(velocity=1.5)
            for k in range(20):
                t=k*.05;e=a.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
                self.assertNotEqual(e.mode,'STOPPED');self.assertGreater(e.v,.25)
            a.reset(velocity=0)
            for k in range(30):
                t=k*.05;e=a.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
            self.assertEqual(e.mode,'STOPPED')
    def test_reset_clears_history(self):
        a=F.make('h03');a._h19_detector.positive[0]=1;a._h19_detector.suspect[0]=True
        a.reset(velocity=3,position=7)
        self.assertEqual(a._h19_detector.positive,[0.,0.]);self.assertEqual(a.v,3);self.assertEqual(a.s,7)
    def test_fusion_and_adaptation_freeze_hook(self):
        # Deterministic isolation: a synthetic weight is not a fitted variant.
        a=F.make('h03');b=F.make('baseline');a.reset(velocity=5);b.reset(velocity=5)
        a.step(0,Sample(0,0),Sample(0,5),Sample(0,5));b.step(0,Sample(0,0),Sample(0,5),Sample(0,5))
        a._h19_weights=lambda *args:[.25,1.]
        d=a.disturbance
        ea=a.step(.1,Sample(.1,0),Sample(.1,5.3),Sample(.1,5.))
        eb=b.step(.1,Sample(.1,0),Sample(.1,5.3),Sample(.1,5.))
        self.assertEqual(ea.front_status,'SEQUENTIAL_DOWNWEIGHTED')
        self.assertEqual(a.disturbance,d);self.assertIsNone(a.adapt_previous)
        self.assertLess(a.v,b.v);self.assertEqual(a._velocity_correction,0.)
    def test_reacquisition_not_accelerated(self):
        a=F.make('h03');b=F.make('baseline');a.reset(velocity=1);b.reset(velocity=1)
        for k in range(40):
            t=k*.05;args=(t,Sample(t,0),Sample(t,4),Sample(t,4))
            self.assertEqual(plain(a.step(*args)),plain(b.step(*args)))
    def test_no_nan_and_no_parameter_changes(self):
        a=F.make('h06');cfg=asdict(a.c)
        for args in self.stream(1000):
            e=a.step(*args)
            self.assertTrue(all(math.isfinite(getattr(e,key)) for key in ('v','s','disturbance','variance_v','variance_s')))
        self.assertEqual(asdict(a.c),cfg)
    def test_forbidden_role_before_file_io(self):
        s=Store()
        for role in ('test','development'):
            bag=s.plan['splits']['test'][0]
            with self.assertRaises(PermissionError):s.load(bag,role)
        self.assertEqual(s.access,[])

if __name__=='__main__':unittest.main()
