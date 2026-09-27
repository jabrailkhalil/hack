import sys,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit as a
import numpy as np
class Tests(unittest.TestCase):
 def test_group_subset_arithmetic(self):
  m=[{'group':'a','bag':'x'},{'group':'a','bag':'x'},{'group':'a','bag':'y'},{'group':'b','bag':'z'}]
  e=np.repeat(np.array([1.,3.,5.,2.])[:,None],6,axis=1);o=a.h54.Objective(m,{'a':2.,'b':4.})
  np.testing.assert_array_equal(o.losses(e),[15.,4.]);r,l,rat,t=o.residual(e,np.zeros(3),True)
  self.assertAlmostEqual(r@r,.5*np.mean([7.5,1])+.5*7.5)
  sub=a.h54.Objective(m[:3],{'a':2.});self.assertEqual(a.parts(sub,np.array([7.5]),np.zeros(3))['J1'],7.5)
 def test_stable_ties_odd_half(self):
  o=a.h54.Objective([{'group':g,'bag':g} for g in ['z','a','m']],{'z':1,'a':1,'m':1})
  self.assertEqual(a.parts(o,np.ones(3),np.zeros(3))['active_top_half_groups'],['a','m'])
 def test_prior_excluded(self):
  o=a.h54.Objective([{'group':'a','bag':'a'}],{'a':1});self.assertEqual(a.parts(o,np.ones(1),np.ones(3),False)['J1'],1.)
 def test_bounds(self):
  theta=np.array([1.,7.,1.]);lo,hi=np.log(np.array([[.05,1,.05],[5,100,5]])/theta);a.bound_check(np.zeros(3),lo,hi)
  np.testing.assert_allclose(theta*np.exp(lo),[.05,1,.05]);np.testing.assert_allclose(theta*np.exp(hi),[5,100,5])
  for x in [hi+1,np.array([np.nan,0,0])]:
   with self.assertRaises(ValueError):a.bound_check(x,lo,hi)
 def test_folds(self):
  fs=json.loads((a.CODE/'FOLDS.json').read_text());allheld=[]
  for f in fs['folds']:
   self.assertFalse(set(f['train_groups'])&set(f['heldout_groups']));self.assertEqual(len(f['train_groups']),12);self.assertEqual(len(f['heldout_groups']),3);allheld+=f['heldout_groups']
  self.assertEqual(sorted(allheld),fs['groups'])
 def test_firewall(self):
  for s in ['CHECK_RESULTS.csv','x/DEVELOPMENT.csv','a.db3','R6_A1/x','H43/atlas']:self.assertTrue(a.forbidden(s))
  self.assertFalse(a.forbidden('.h61_inputs/windows/windows.npz'))
 def test_budget_before_predictor(self):
  o=a.Audit.__new__(a.Audit);o.calls=900;o.lo=np.full(3,-1);o.hi=np.full(3,1)
  with self.assertRaises(RuntimeError):o.call(np.zeros(3),'nonexistent','budget')
 def test_fingerprint(self):
  x=np.arange(10,dtype=float);self.assertEqual(a.fingerprint(x),a.fingerprint(x.copy()));self.assertNotEqual(a.fingerprint(x),a.fingerprint(x+1))
 def test_lock_and_fit_only(self):
  a.verify();s,t,m,idx=a.load_fit();self.assertEqual(len(m),141);self.assertTrue(all(x['fold']=='fit' for x in m));self.assertEqual(len(s),len(t))
 def test_solver_contract(self):self.assertEqual(a.OPTIONS,{'xtol':1e-6,'ftol':1e-8,'maxfev':130})
if __name__=='__main__':unittest.main()
