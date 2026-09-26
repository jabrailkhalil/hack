"""Diagnostic tests only: no augmented observer is claimed to be implemented."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import foundation as f

class FoundationTests(unittest.TestCase):
    def probe(self):
        c, ro = f.profile()
        return f.Probe(c, readout=ro, check_state=True)

    def events(self, n=100):
        return np.asarray([(i*.1, ch, .05 if ch==0 else 5.+.002*i)
                           for i in range(n) for ch in range(3)], float)

    def test_pinned_integrity(self):
        self.assertTrue(f.integrity()['passed'])

    def test_exact_profile_not_config_defaults(self):
        c, ro=f.profile()
        self.assertEqual(c.common_mode_quarantine_s, 1.5)
        self.assertEqual(c.adaptation_tau_s,.5)
        self.assertNotEqual(c.actuator_tau_s,f.Config().actuator_tau_s)
        self.assertEqual((ro.gain,ro.holdoff_s),(1.,.5))

    def test_mixed_stream_exact_all_baseline_state(self):
        o=self.probe()
        for i in range(2000):
            t=i*.05; ts=(i//2)*.1; phase=i%400
            z=5.+.05*np.sin(ts)
            cmd=f.Sample(ts, -.2 if phase>300 else .1)
            front=rear=f.Sample(ts,z)
            if 90<phase<130: front=rear=None
            if 160<phase<190: front=rear=f.Sample(ts, z+5.)
            if 200<phase<230: front=rear=f.Sample(ts, z-3.)
            if 240<phase<260: front=rear=f.Sample(ts,0.)
            if phase==280: front=f.Sample(t+1.,z)
            if phase==290: cmd=f.Sample(t-1.,.1)
            if phase==299: front=f.Sample(ts,float('nan'))
            o.step(t,cmd,front,rear)
        self.assertEqual(set(vars(o))-set(vars(o.reference)),{'check_state','reference','probe'})

    def test_duplicate_never_produces_probe(self):
        o=self.probe()
        for i in range(40):
            t=i*.05;ts=(i//2)*.1
            o.step(t,f.Sample(ts,0.),f.Sample(ts,5.),f.Sample(ts,5.))
            if i%2:self.assertIsNone(o.probe)

    def test_future_and_stale_not_in_diagnostic(self):
        o=self.probe();o.reset(velocity=5.)
        o.step(0.,f.Sample(0.,0.),f.Sample(.1,5.),f.Sample(.1,5.))
        self.assertIsNone(o.probe)
        o.step(.1,f.Sample(-1.,0.),f.Sample(.1,5.),f.Sample(.1,5.))
        self.assertIsNone(o.probe)

    def test_explicit_reset_clears_probe_and_base_state(self):
        o=self.probe();o.reset(velocity=5.)
        o.step(0.,f.Sample(0.,0.),f.Sample(0.,5.),f.Sample(0.,5.))
        o.step(.1,f.Sample(.1,0.),f.Sample(.1,5.),f.Sample(.1,5.))
        self.assertIsNotNone(o.probe)
        o.reset();self.assertIsNone(o.probe)
        for k,v in vars(o.reference).items():self.assertEqual(getattr(o,k),v)

    def test_causal_prefix_and_no_time_rewrite(self):
        e=self.events();a,_,_=f.trace(e,check_state=True)
        changed=e.copy();changed[changed[:,0]>5.,2]*=-1
        b,_,_=f.trace(changed,check_state=True)
        np.testing.assert_array_equal(a[a[:,0]<=5.],b[b[:,0]<=5.])
        self.assertTrue(np.all(np.diff(a[:,f.IDX['pair_t']])>0))

    def test_correlations_do_not_bridge_gaps_segments_or_bags(self):
        a=np.zeros((5,len(f.COLUMNS)));a[:,f.IDX['pair_t']]=[0,.1,.4,.5,.6]
        a[:,f.IDX['segment']]=[0,0,1,2,2]
        a[:,f.IDX['raw']]=[.1,.2,.3,.1,.2]
        stats=f.statistics([a,a],'raw','trusted',np.zeros(9))
        self.assertEqual(stats['pairs'],4)

    def test_empty_diagnostics_are_missing_not_zero(self):
        s=f.statistics([np.empty((0,len(f.COLUMNS)))],'raw','tight',np.zeros(9))
        self.assertIsNone(s['rms']);self.assertIsNone(s['lag1_correlation'])
        self.assertEqual(s['pairs'],0)

    def test_group_partition_is_deterministic_and_disjoint(self):
        records=json.loads((f.ROOT/'research/split_v3.json').read_text())['records']
        p=f.partition(records)
        self.assertEqual(p,f.partition(list(reversed(records))))
        self.assertFalse(set(p['check']) & set(p['fitting']))
        self.assertEqual((len(p['fitting']),len(p['check'])),(20,7))

    def test_check_targets_do_not_fit_nuisance(self):
        records=[{'bag':str(i),'group':'g'+str(i),'split':'train'} for i in range(8)]
        traces={}
        for r in records:
            a=np.zeros((300,len(f.COLUMNS)))
            a[:,f.IDX['pair_t']]=np.arange(300)*.1
            a[:,f.IDX['age_adjusted']]=np.sin(np.arange(300)*.1)*.02
            a[:,f.IDX['raw']]=a[:,f.IDX['age_adjusted']]
            a[:,f.IDX['steady']]=1;a[:,f.IDX['tight']]=1
            traces[r['bag']]=a
        before=f.analyze(traces,records)[0]['nuisance']['coefficient']
        check=f.partition(records)['check']
        for r in records:
            if r['group'] in check:traces[r['bag']][:,f.IDX['age_adjusted']]+=123
        after=f.analyze(traces,records)[0]['nuisance']['coefficient']
        self.assertEqual(before,after)

    def test_test_and_validation_roles_denied_before_io(self):
        store=f.ev.ex.Store(Path('/nonexistent-data'))
        for role in ('test','validation','development'):
            bag=store.plan['splits'][role][0]
            with patch.object(f.ev.ex,'digest',side_effect=AssertionError('unexpected file read')):
                with self.assertRaises(PermissionError):store.load(bag,'train')

    def test_low_speed_zero_lock_and_quarantine_remain_exact(self):
        for initial in (1.5,5.):
            o=self.probe();o.reset(velocity=initial)
            for i in range(160):
                t=i*.05;ts=(i//2)*.1
                z=initial if t<2. else (0. if initial<2 else initial+5.)
                out=o.step(t,f.Sample(ts,0.),f.Sample(ts,z),f.Sample(ts,z))
                if initial<2 and 2.<t<3.:
                    self.assertNotEqual(out.mode,'STOPPED')
            if initial>=2:self.assertGreater(o.reacquire_blocked_until,2.)

if __name__=='__main__':unittest.main()
