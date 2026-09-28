import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import profile,VehicleStore,ev
from history import History,command_mode
from probe import replay
from reserve_odometry.core import Sample

class TestFoundation(unittest.TestCase):
    def setUp(self): self.c,_=profile()
    def test_profile(self): self.assertEqual(self.c.common_mode_quarantine_s,1.5)
    def test_modes(self):
        self.assertEqual(command_mode(Sample(1,.2),1,self.c),1)
        self.assertEqual(command_mode(Sample(1,-.2),1,self.c),-1)
        self.assertEqual(command_mode(Sample(1,0),1,self.c),0)
    def test_future_command(self): self.assertIsNone(command_mode(Sample(1.1,.2),1,self.c))
    def test_stale_command(self): self.assertIsNone(command_mode(Sample(0,.2),1,self.c))
    def test_nonfinite_command(self): self.assertIsNone(command_mode(Sample(1,math.nan),1,self.c))
    def test_short_history(self): self.assertFalse(History().checkpoint(1,0,.2,.02)['eligible'])
    def test_window(self):
        h=History();h.samples.extend([(i/10,.1) for i in range(9)])
        p=h.checkpoint(1,.3,.2,.02)
        self.assertTrue(p['eligible']);self.assertAlmostEqual(p['checkpoint'],.1)
    def test_expiry(self):
        h=History();h.samples.extend([(i/10,.1) for i in range(9)])
        self.assertFalse(h.checkpoint(2,.3,.2,.02)['eligible'])
    def test_stability(self):
        h=History();h.samples.extend([(.4,-.3),(.5,0.),(.6,.3),(.7,.1),(.8,.1)])
        p=h.checkpoint(1,.3,.2,.02)
        self.assertEqual(p['reason'],'unstable')
    def test_count_bound(self):
        h=History();h.samples.extend([(i,.1) for i in range(100)])
        self.assertEqual(len(h.samples),16)
    def test_duplicate_does_not_open_loss(self):
        h=History();e=SimpleNamespace(mode='MODEL_ONLY',front_status='DUPLICATE_OR_OLD',rear_status='DUPLICATE_OR_OLD',disturbance=0)
        _,_,opened=h.observe(1,Sample(1,.2),None,None,e,None,0,self.c,.02)
        self.assertIsNone(opened)
    def test_real_rejection_opens_loss(self):
        h=History();e=SimpleNamespace(mode='MODEL_ONLY',front_status='MISSING_OR_STALE',rear_status='DUPLICATE_OR_OLD',disturbance=0)
        _,_,opened=h.observe(1,Sample(1,.2),None,None,e,None,0,self.c,.02)
        self.assertEqual(opened['ticks'],1)
    def test_mode_change_discards_history(self):
        h=History();h.mode=1;h.samples.extend([(i/10,.1) for i in range(9)])
        e=SimpleNamespace(mode='MODEL_ONLY',front_status='MISSING_OR_STALE',rear_status='MISSING_OR_STALE',disturbance=.3)
        _,_,opened=h.observe(1,Sample(1,-.2),None,None,e,None,0,self.c,.02)
        self.assertFalse(opened['proposals']['0.2']['eligible'])
    def test_model_only_duplicates_continue_existing_episode(self):
        h=History();e=SimpleNamespace(mode='MODEL_ONLY',front_status='MISSING_OR_STALE',rear_status='MISSING_OR_STALE',disturbance=0)
        h.observe(1,Sample(1,.2),None,None,e,None,0,self.c,.02)
        e.front_status=e.rear_status='DUPLICATE_OR_OLD'
        h.observe(1.05,Sample(1,.2),None,None,e,None,0,self.c,.02)
        self.assertEqual(h.episode['ticks'],2)
    def test_forbidden_roles_before_sql(self):
        store=VehicleStore()
        with patch('sqlite3.connect') as sql:
            for role in ('validation','test'):
                with self.assertRaises(PermissionError):store.load(store.plan['splits'][role][0],role)
            sql.assert_not_called()
    def test_no_train_gnss(self):
        store=VehicleStore()
        with patch('sqlite3.connect') as sql:
            with self.assertRaises(PermissionError):store.load(store.plan['splits']['train'][0],'train',reference=True)
            sql.assert_not_called()
    def test_mismatched_role_before_sql(self):
        store=VehicleStore()
        with patch('sqlite3.connect') as sql:
            with self.assertRaises(PermissionError):store.load(store.plan['splits']['validation'][0],'development')
            sql.assert_not_called()
    def test_native_equivalence_synthetic_mixed(self):
        events=[]
        for i in range(3000):
            t=i*.05;u=.2 if i%400<200 else -.1
            events.append((t,0,u))
            if i%2==0 and not 800<i<900:
                v=2+.1*math.sin(t)
                if 1400<i<1420:v+=5
                if 1700<i<1740:v=0
                events.extend([(t,1,v),(t,2,v)])
        r=replay(ev.np.array(events),.02)
        self.assertGreater(r['ticks'],2900)
        self.assertEqual(r['runtime']['causal_errors'],0)
        self.assertLessEqual(r['history_peak'],16)

if __name__=='__main__':unittest.main()
