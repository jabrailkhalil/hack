import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fit
import numpy as np
from reserve_odometry.core import Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver
from reserve_odometry.timeline import Timeline

class FitTests(unittest.TestCase):
    def fixture(self):
        t=np.arange(201)*.05
        w=np.c_[t,t,np.where(t<7, .4,-.3),t,3+.03*t,t,3+.03*t]
        return w[None]
    def test_masked_row_not_bridged(self):
        v=fit.teacher_grid(np.array([0,100000000,200000000]),np.array([1.,np.nan,1.]),np.array([True,False,True]),np.array([50000000,100000000,150000000]))
        self.assertTrue(np.isnan(v).all())
    def test_gap_no_extrapolation(self):
        v=fit.teacher_grid(np.array([0,300000000]),np.array([0.,1.]),np.array([True,True]),np.array([-1,150000000,300000001]))
        self.assertTrue(np.isnan(v).all())
    def test_exact_zero_valid(self):
        v=fit.teacher_grid(np.array([10,100000010]),np.array([0.,1.]),np.array([True,True]),np.array([10,50000010]))
        np.testing.assert_array_equal(v,[0.,.5])
    def test_nonmonotone_rejected(self):
        with self.assertRaises(ValueError):fit.teacher_grid(np.array([1,1]),np.ones(2),np.ones(2,bool),np.array([1]))
    def test_unsigned_loss(self):
        w=self.fixture(); pred=fit.Predictor(w).predict(np.zeros(3))
        a=fit.errors(pred,np.abs(pred),w);b=fit.errors(-pred,np.abs(pred),w)
        for x,y in zip(a,b):np.testing.assert_allclose(x,y,atol=1e-14)
    def test_constant_prefix(self):
        w=self.fixture();v=np.full((1,101),2.)
        np.testing.assert_allclose(fit.prefixes(v,w),[[1.,4.,10.]],atol=1e-13)
    def test_balancing(self):
        m=[dict(group='a',bag='x')]*3+[dict(group='a',bag='y')]+[dict(group='b',bag='z')]*2
        w=fit.balanced_weights(m);self.assertAlmostEqual(sum(w[:4]),.5);self.assertAlmostEqual(sum(w[:3]),.25);self.assertAlmostEqual(sum(w),1.)
    def test_future_wheels_not_used_by_forecast(self):
        w=self.fixture();p=fit.Predictor(w).predict(np.zeros(3));other=w.copy();other[:,101:,4]=25;other[:,101:,6]=-25
        np.testing.assert_array_equal(p,fit.Predictor(other).predict(np.zeros(3)))
    def test_future_command_does_not_change_prefix(self):
        w=self.fixture();p=fit.Predictor(w).predict(np.zeros(3));other=w.copy();other[:,151:,2]=1
        q=fit.Predictor(other).predict(np.zeros(3));np.testing.assert_array_equal(p[:,:51],q[:,:51])
    def test_own_configuration_warmup(self):
        w=self.fixture();p=fit.Predictor(w).predict(np.zeros(3));q=fit.Predictor(w).predict(np.array([.1,0,.1]))
        self.assertFalse(np.array_equal(p,q));self.assertNotEqual(p[0,0],q[0,0])
    def test_scalar_independent_timeline(self):
        w=self.fixture();base,r,ops=fit.profile();p=fit.Predictor(w).predict(np.zeros(3))[0]
        tl=Timeline(GuardedReadoutObserver(base,readout=r),rate_hz=20,delay_s=0);out=[]
        for k,row in enumerate(w[0]):
            for ch,j in enumerate((1,3,5)):
                if k<=100 or ch==0:tl.ingest(ch,Sample(float(row[j]),float(row[j+1])))
            if k==101:tl.held[1:]=[None,None];tl.queues[1:]=[[],[]]
            for e,_ in tl.advance(now=float(row[0])):
                if k>=100:out.append(e.v)
        np.testing.assert_array_equal(p,out)
    def test_disabled_parameters_exact(self):
        c,_,_=fit.profile();self.assertEqual(vars(c),vars(fit.with_effective(c,fit.effective(c))))
    def test_no_target_in_predictor_interface(self):
        import inspect
        self.assertEqual(list(inspect.signature(fit.Predictor.predict).parameters),['self','logratio','indices'])
if __name__=='__main__':unittest.main()
