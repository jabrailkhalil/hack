import math
from pathlib import Path
import sys
import unittest
import numpy as np
from common import baseline, profile, Sample, Store
from foundation import Probe, segments, IDX, COLUMNS, moments, public, verdict
from numerics import targets, solve_tridiagonal, GHistory, FLOOR

class FoundationTests(unittest.TestCase):
    def test_solver_dense_reference(self):
        rng=np.random.default_rng(3301)
        for n in range(1,7):
            c=np.diag(np.full(n,2+FLOOR))+np.diag(np.full(n-1,-1),1)+np.diag(np.full(n-1,-1),-1)
            self.assertGreater(np.linalg.eigvalsh(c).min(),0)
            for _ in range(30):
                b=rng.normal(size=n)
                np.testing.assert_allclose(solve_tridiagonal(b),np.linalg.solve(c,b),atol=1e-12,rtol=1e-12)

    def test_affine_variable_dt(self):
        ts=[0,.07,.18,.27,.40]
        for d in [-.6,.2,.6]:
            gls,ols,var=targets(ts,[d*h for h in np.diff(ts)])
            self.assertAlmostEqual(gls,d);self.assertAlmostEqual(ols,d);self.assertGreater(var,0)

    def test_scale_cancellation(self):
        a=targets([0,.1,.2,.3],[.03,.01,-.02],.1)
        b=targets([0,.1,.2,.3],[.03,.01,-.02],.2)
        self.assertEqual(a[:2],b[:2]);self.assertAlmostEqual(b[2],4*a[2])

    def test_equal_two_increments_same_point_target(self):
        g,o,_=targets([0,.1,.2],[.03,-.01]);self.assertAlmostEqual(g,o)

    def test_four_increment_weights(self):
        values=[]
        for i in range(4):
            y=[0.]*4;y[i]=1.
            values.append(targets([0,.1,.2,.3,.4],y)[0])
        np.testing.assert_allclose(values,[2.,3.,3.,2.],atol=2e-6)

    def test_iid_endpoint_covariance(self):
        e=np.random.default_rng(3302).normal(0,.1,(100000,5));y=np.diff(e,axis=1)
        c=np.cov(y,rowvar=False)
        self.assertAlmostEqual(c[0,0],.02,delta=.0003)
        self.assertAlmostEqual(c[0,1],-.01,delta=.0003)
        self.assertAlmostEqual(c[0,2],0.,delta=.0003)
        h=np.full(4,.1);w=np.linalg.solve(.01*(np.diag([2]*4)+np.diag([-1]*3,1)+np.diag([-1]*3,-1)),h);w/=h@w
        self.assertAlmostEqual(float(np.var(y@w)),.1,delta=.002)

    def test_bad_solve_inputs(self):
        for y in [[],[0.]*7,[float('nan')]]:
            with self.assertRaises(ValueError):solve_tridiagonal(y)
        with self.assertRaises(ValueError):targets([0,.01],[0.])

    def test_piecewise_fractional_integral(self):
        h=GHistory()
        for t in [0,.05,.10,.15,.20]:h.add(t,2+3*t,True)
        self.assertAlmostEqual(h.integral(.023,.173),2*(.173-.023)+1.5*(.173**2-.023**2))

    def test_history_does_not_extrapolate(self):
        h=GHistory();h.add(0,0,True);h.add(.1,1,True)
        for lo,hi in [(-.01,.1),(0,.101),(0,0)]:
            with self.assertRaises(ValueError):h.integral(lo,hi)

    def test_stale_clipped_and_gap(self):
        h=GHistory();h.add(0,0,True);h.add(.1,1,False)
        with self.assertRaises(ValueError):h.integral(0,.1)
        h=GHistory();h.add(0,0,True);h.add(.3,1,True)
        with self.assertRaises(ValueError):h.integral(0,.3)

    def test_bounded_history(self):
        h=GHistory()
        for k in range(15000):
            t=k*.001;h.add(t,0,True)
            self.assertLessEqual(len(h.points),32)
            self.assertLessEqual(t-h.points[0][0],.75+1e-9)

    def test_probe_exact_full_state_and_future_samples(self):
        p=Probe();b=baseline()
        for k in range(4000):
            t=k*.05;u=Sample(t,.2 if k%600<300 else 0.)
            w=Sample(t,3+.15*math.sin(t))
            if 500<k%1200<520:w=None
            if k%83==0:w=Sample(t+.02,3.)
            e=p.step(t,u,w,w);r=b.step(t,u,w,w)
            self.assertEqual(e,r)
            for name,value in vars(b).items():self.assertEqual(getattr(p,name),value,name)
        self.assertTrue(p.rows)
        self.assertLessEqual(len(p.pairs),7)

    def test_probe_prefix_and_duplicate(self):
        p=Probe();q=Probe()
        for k in range(100):
            t=k*.05;stamp=(k//2)*.1;w=Sample(stamp,4.)
            args=(t,Sample(t,.2),w,w)
            self.assertEqual(p.step(*args),q.step(*args))
        n=len(p.rows)
        for k in range(100,150):p.step(k*.05,Sample(k*.05,.2),None,None)
        np.testing.assert_array_equal(p.rows[:n],q.rows)

    def test_reset_same_as_baseline(self):
        p=Probe();b=baseline()
        for o in [p,b]:o.step(0,Sample(0,.1),Sample(0,2),Sample(0,2));o.reset(velocity=3,position=10)
        self.assertEqual(p.step(1),b.step(1))
        with self.assertRaises(ValueError):p.step(1)

    def test_no_cross_gap_segments(self):
        a=np.zeros((80,len(COLUMNS)));a[:,1]=np.arange(80)*.1;a[:,2]=.1;a[:,IDX['steady']]=1
        a[40:,0]=1
        self.assertEqual([len(b) for b in segments(a,True)],[40,40])
        a[20,IDX['steady']]=0
        self.assertEqual([len(b) for b in segments(a,True)],[40])

    def test_denied_roles_before_io(self):
        s=Store(Path('/tmp/H33-test-should-not-write.json'))
        for role in ['test','train','development','validation']:
            bag=s.plan['splits']['test'][0]
            with self.assertRaises(PermissionError):s.load(bag,role)

    def test_gate_requires_negative_structure(self):
        groups={}
        for k in range(3):
            groups[str(k)]={'controlled':{'residual_accel':dict(lag1_pairs=400,lag1=.4,lag2=.3,sigma_proxy_mps=.01)},
                            'windows':{'40':dict(changed_vs_unweighted=100)}}
        r=verdict(groups);self.assertFalse(r['foundation_passed']);self.assertIn('nonlocal_serial_structure_lag2',r['reasons'])
        for s in groups.values():s['controlled']['residual_accel'].update(lag1=-.4,lag2=.05)
        self.assertTrue(verdict(groups)['foundation_passed'])

if __name__=='__main__':unittest.main(verbosity=2)
