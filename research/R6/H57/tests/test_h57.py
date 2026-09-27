import unittest
from pathlib import Path
import sys
from fractions import Fraction
import tempfile
import inspect
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run as h

class SelectionTests(unittest.TestCase):
    def test_empty_small(self):
        self.assertEqual(h.quantile_indices(0),[])
        self.assertEqual(h.quantile_indices(1),[0])
        self.assertEqual(h.quantile_indices(2),[0,1])
        with self.assertRaises(ValueError):h.quantile_indices(-1)
    def test_exact_rational_nearest_all_sizes(self):
        # Independent Fraction/argmin oracle, no rounding shortcut.
        for n in range(3,300):
            expected=[min(range(n),key=lambda k:(abs(Fraction(k)-Fraction(q*(n-1),3)),k)) for q in (1,2)]
            if n==3:
                expected=list(min(((i,j) for i in range(n) for j in range(i+1,n)),
                    key=lambda ij:(sum((Fraction(ij[q-1])-Fraction(q*(n-1),3))**2 for q in (1,2)),ij)))
            self.assertEqual(h.quantile_indices(n),expected)
    def test_no_duplicate_selection(self):
        for n in range(3,10001):
            idx=h.quantile_indices(n);self.assertEqual(len(set(idx)),2)
            self.assertTrue(0<=idx[0]<idx[1]<n)
    def fixture(self):
        return [dict(bag=b,group=b,phase=p,fold='fit',anchor_s=float(k*5),wire_representative=b)
                for b in ('a','b') for p in h.PHASES for k in range(20)]
    def test_equal_count_and_bins(self):
        m=self.fixture();a=h.select(m,'C0');b=h.select(m,'C1')
        self.assertEqual(len(a),12);self.assertEqual(len(b),12)
        ga=lambda ids:h.Counter((m[i]['bag'],m[i]['phase']) for i in ids)
        self.assertEqual(ga(a),ga(b))
    def test_duplicate_stream_not_selected(self):
        m=self.fixture();m.extend(dict(x,bag='duplicate',wire_representative='a') for x in m[:20])
        for policy in ('C0','C1'):self.assertTrue(all(m[i]['bag']!='duplicate' for i in h.select(m,policy)))
    def test_error_values_do_not_affect_selection(self):
        m=self.fixture();a=h.select(m,'C1')
        for i,x in enumerate(m):x.update(residual=1e12-i,teacher_quality=1/i if i else 0)
        self.assertEqual(a,h.select(m,'C1'))
    def test_order_independent(self):
        m=self.fixture();rng=np.random.default_rng(8);p=rng.permutation(len(m));rev=[m[i] for i in p]
        for policy in ('C0','C1'):
            a=[m[i] for i in h.select(m,policy)];b=[rev[i] for i in h.select(rev,policy)];self.assertEqual(a,b)
    def test_unfair_counts_rejected(self):
        m=self.fixture();a=h.select(m,'C0');b=h.select(m,'C1')
        with self.assertRaises(AssertionError):h.foundation(m,a,b[:-1])
    def test_foundation_requires_check(self):
        m=self.fixture();gate,_=h.foundation(m,h.select(m,'C0'),h.select(m,'C1'));self.assertFalse(gate['passed'])

class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.cfg,_,_=h.profile();t=np.arange(201)*.05
        self.w=np.c_[t,t,np.full(201,.3),t,np.full(201,3.),t,np.full(201,3.)];self.y=np.full(101,3.)
    def test_healthy(self):self.assertEqual(h.eligible_reason(self.w,self.y,self.cfg),'eligible')
    def test_finite(self):
        self.w[4,4]=np.nan;self.assertEqual(h.eligible_reason(self.w,self.y,self.cfg),'missing_or_grid')
    def test_grid(self):
        self.w[3,0]+=.01;self.assertEqual(h.eligible_reason(self.w,self.y,self.cfg),'missing_or_grid')
    def test_future(self):
        self.w[3,3]+=.001;self.assertEqual(h.eligible_reason(self.w,self.y,self.cfg),'stale_or_future')
    def test_stale(self):
        self.w[3,1]-=self.cfg.command_timeout_s+.001;self.assertEqual(h.eligible_reason(self.w,self.y,self.cfg),'stale_or_future')
    def test_mismatch(self):
        self.w[5,6]+=self.cfg.disagreement_mps+.001;self.assertEqual(h.eligible_reason(self.w,self.y,self.cfg),'wheel_or_command_invalid')
    def test_command_range(self):
        self.w[5,2]=1.1;self.assertEqual(h.eligible_reason(self.w,self.y,self.cfg),'wheel_or_command_invalid')
    def test_motion(self):
        self.w[:,4]=self.w[:,6]=0.;self.assertEqual(h.eligible_reason(self.w,self.y,self.cfg),'no_motion')
    def test_teacher_hole(self):
        self.y[15]=np.nan;self.assertEqual(h.eligible_reason(self.w,self.y,self.cfg),'teacher_missing_or_masked')
    def test_teacher_residual_not_eligibility(self):
        self.assertEqual(h.eligible_reason(self.w,self.y+100,self.cfg),'eligible')
    def test_phase_anchor_only(self):
        self.w[99,2]=-.4;self.assertEqual(h.phase(self.w[100],self.cfg),'traction')
    def test_future_wheels_not_forecast_inputs(self):
        samples=self.w[None];pred=h.h44.Predictor(samples).predict(np.zeros(3));samples=samples.copy();samples[:,101:,[4,6]]=999
        np.testing.assert_array_equal(pred,h.h44.Predictor(samples).predict(np.zeros(3)))
    def test_predictor_has_no_target_argument(self):
        self.assertEqual(list(inspect.signature(h.h44.Predictor.predict).parameters),['self','logratio','indices'])
    def test_common_score_independent_equation(self):
        sample=self.w[None];pred=np.full((1,101),4.);target=np.full((1,101),3.)
        v=h.metrics(pred,target,sample,[dict(bag='b',group='g')]);self.assertAlmostEqual(v['velocity_rms'],1.)
        scale=h.h44.SCALES;expected=np.sqrt(np.mean(1/scale**2));self.assertAlmostEqual(v['combined_rms'],expected,places=12)
    def test_no_empty_denominator_zero(self):self.assertIsNone(h.metrics(None,None,None,[]))

if __name__=='__main__':unittest.main()
