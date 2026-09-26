import math
import unittest
from unittest.mock import patch
from dataclasses import asdict
from audit import *


class AuditTests(unittest.TestCase):
    def test_exact_profiles(self):
        i=integrity();self.assertEqual(i['h36_profile_blob'],H36_BLOB)
        self.assertEqual(len(i['changed_coefficients']),3)
    def test_role_before_filesystem_io(self):
        st=DevelopmentStore(Path('/nonexistent'))
        for role in ('train','validation','test'):
            with patch('sqlite3.connect',side_effect=AssertionError('SQL must not run')):
                with self.assertRaises(PermissionError):st.load(st.plan['splits'][role][0],role)
    def test_passive_all_state_4000(self):
        cfg,read=profile();a=Capture(cfg);b=GuardedReadoutObserver(cfg,readout=read)
        for i in range(4000):
            t=.05*i;u=Sample(t,math.sin(t/6)*.4);v=2+.5*math.sin(t/8)
            f,r=(Sample(t,v),Sample(t+.0,v+.002)) if i%3 else (None,None)
            self.assertEqual(a.step(t,u,f,r),b.step(t,u,f,r))
            self.assertEqual(vars(a.o),vars(b))
    def test_coherent_and_hold_prefault(self):
        cfg,_=profile();fault={'start':3.,'end':5.,'kind':'dropout'}
        obs={n:Capture(cfg,n,fault) for n in ('main','coherent','hold_d')}
        d0=None
        for i in range(150):
            t=.05*i;u=Sample(t,.4); f=r=Sample(t,3.) if t<3. or t>=5. else None
            if t==3.:d0=obs['main'].o.disturbance
            result={n:o.step(t,u,f,r) for n,o in obs.items()}
            if t<3.:
                self.assertEqual(vars(obs['main'].o),vars(obs['coherent'].o))
                self.assertEqual(vars(obs['main'].o),vars(obs['hold_d'].o))
            if 3.<=t<5.:self.assertEqual(result['hold_d'].disturbance,d0)
        self.assertEqual(obs['coherent'].switch_t,3.)
        self.assertEqual(obs['hold_d'].hold_ticks,40)
        self.assertEqual(obs['coherent'].prefix.digest(),obs['main'].prefix.digest())
        self.assertEqual(obs['hold_d'].prefix.digest(),obs['main'].prefix.digest())
    def test_stop_priority(self):
        cfg,_=profile();f={'start':.5,'end':4.,'kind':'lock'}
        o=Capture(cfg,'hold_d',f)
        for i in range(80):
            t=i*.05;e=o.step(t,Sample(t,0.),Sample(t,0.),Sample(t,0.))
        self.assertEqual(e.mode,'STOPPED');self.assertFalse(o.hold_allowed)
        self.assertEqual(e.disturbance,0.)
    def test_no_distance_reset_at_recovery(self):
        cfg,_=profile();f={'start':2.,'end':4.,'kind':'dropout'}
        a=Capture(cfg,'coherent',f);b=Capture(cfg,'main',f)
        for i in range(160):
            t=i*.05;u=Sample(t,.3);wh=Sample(t,3.) if t<2 or t>=4 else None
            a.step(t,u,wh,wh);b.step(t,u,wh,wh)
        x,y=a.array(),b.array();dv=x[:,1]-y[:,1];ds=x[:,2]-y[:,2]
        np.testing.assert_allclose(ds-ds[0],np.r_[0,np.cumsum(.5*(dv[1:]+dv[:-1])*np.diff(x[:,0]))],atol=1e-11,rtol=0)
    def test_affine_fractional_integral(self):
        t=np.arange(0,2.01,.05);e=3*t-2
        r=signed_integral(t,e,.013,1.983)
        expected=1.5*(1.983**2-.013**2)-2*(1.983-.013)
        self.assertAlmostEqual(r['full_integral_m'],expected,12)
    def test_reference_gap_not_bridged(self):
        t=np.arange(0,2.01,.05);e=np.ones(len(t));e[10]=np.nan
        r=signed_integral(t,e,0.,2.)
        self.assertIsNone(r['full_integral_m']);self.assertAlmostEqual(r['covered_s'],1.9)
        self.assertAlmostEqual(r['integral_on_covered_edges_m'],1.9)
    def test_time_gap_not_bridged(self):
        t=np.array([0.,.05,.10,.3,.35]);r=signed_integral(t,np.ones(5),0,.35)
        self.assertAlmostEqual(r['covered_s'],.15);self.assertIsNone(r['full_integral_m'])
    def test_missing_reference(self):
        t=np.arange(0,1,.05);r=signed_integral(t,np.full(len(t),np.nan),0.,.95)
        self.assertIsNone(r['full_integral_m']);self.assertIsNone(r['integral_on_covered_edges_m'])
    def test_injection_preserves_command_and_input(self):
        es=np.array([[t,c,2.] for t in np.arange(0,3,.05) for c in (0,1,2)])
        before=es.copy();f=dict(kind='dropout',start=1.,end=2.)
        a=inject(es,f);np.testing.assert_array_equal(es,before)
        np.testing.assert_array_equal(es[es[:,1]==0],a[a[:,1]==0])
    def test_prefix_and_future(self):
        cfg,read=profile();a=Capture(cfg);b=GuardedReadoutObserver(cfg,readout=read)
        for i in range(100):
            t=i*.05
            es=(t,Sample(t,.2),Sample(t+1,2),Sample(t+1,2))
            self.assertEqual(a.step(*es),b.step(*es))
    def test_reset_initial_state(self):
        cfg,_=profile();a=Capture(cfg,'hold_d',dict(start=1.,end=2.))
        for i in range(100):
            t=i*.05;a.step(t,Sample(t,0.),Sample(t,1.),Sample(t,1.))
        a.reset();self.assertIsNone(a.t);self.assertFalse(a.started);self.assertEqual(a.rows,[])
    def test_input_timestamp_failure_unchanged(self):
        cfg,_=profile();a=Capture(cfg)
        a.step(1.,Sample(1.,0),Sample(1.,1),Sample(1.,1))
        with self.assertRaises(ValueError):a.step(1.)
    def test_dense_independent_integrals(self):
        rng=np.random.default_rng(43)
        for _ in range(100):
            t=np.cumsum(rng.uniform(.01,.05,80));e=rng.normal(size=80)
            lo,hi=sorted(rng.uniform(t[0],t[-1],2))
            selected=np.r_[lo,t[(t>lo)&(t<hi)],hi]
            vals=np.interp(selected,t,e)
            self.assertAlmostEqual(signed_integral(t,e,lo,hi)['full_integral_m'],float(np.trapezoid(vals,selected)),12)

if __name__=='__main__':unittest.main(verbosity=2)
