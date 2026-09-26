import copy, dataclasses, math, random, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import *
from factory import build,runtime,PRIVATE
F=runtime.advance_release

def norm(x):
 if dataclasses.is_dataclass(x):return {k:norm(v) for k,v in dataclasses.asdict(x).items()}
 if isinstance(x,(list,tuple)):return [norm(v) for v in x]
 if isinstance(x,dict):return {k:norm(v) for k,v in x.items()}
 return x

class H35Tests(unittest.TestCase):
 def test_source_identity(self):self.assertEqual(len(verify_sources()),301)
 def test_profile(self):
  o=build(.5);self.assertEqual(o.c.common_mode_quarantine_s,1.5);self.assertEqual(o.readout.gain,1.)
 def test_ratio_invalid(self):
  for q in (0.,-1.,3.,float('nan'),float('inf')):
   with self.assertRaises(ValueError):build(q)
 def test_initial_zero(self):
  for r in (-1.,0.,1.):
   for q in (.5,2.):self.assertEqual(F(0.,r,.1,.4,q),r*(1-math.exp(-.1/.4)))
 def test_traction_to_coast(self):self.assertAlmostEqual(F(1,0,.1,.4,.5),math.exp(-.5),14)
 def test_brake_to_coast(self):self.assertAlmostEqual(F(-1,0,.1,.4,2),-math.exp(-.125),14)
 def test_repeated_zero(self):
  for q in (.5,2.):
   x=1.
   for _ in range(200):x=F(x,0,.05,.4,q);self.assertGreaterEqual(x,0.)
   self.assertAlmostEqual(x,math.exp(-10/(.4*q)),13)
 def test_zero_duration(self):
  for x in (-1.,0.,1.):self.assertEqual(F(x,-x,0.,.4,.5),x)
 def test_release_same_sign(self):
  for s in (-1,1):self.assertAlmostEqual(F(s,.2*s,.1,.4,.5),s*(.2+.8*math.exp(-.5)))
 def test_growth_exact(self):
  for x,r in ((.1,1.),(-.1,-1.),(1.,1.)):
   for q in (.5,2.):self.assertEqual(F(x,r,.1,.4,q),x+(1-math.exp(-.1/.4))*(r-x))
 def test_opposite_before_crossing(self):
  for q in (.5,2.):self.assertAlmostEqual(F(1.,-1.,.01,.4,q),-1+2*math.exp(-.01/(.4*q)),14)
 def test_opposite_after_crossing(self):
  for q in (.5,2.):
   t0=.4*q*math.log(2);dt=t0+.1
   self.assertAlmostEqual(F(1.,-1.,dt,.4,q),-(1-math.exp(-.1/.4)),14)
 def test_crossing_continuity(self):
  for q in (.5,2.):
   t0=.4*q*math.log(2)
   self.assertAlmostEqual(F(1.,-1.,t0,.4,q),0.,14)
   self.assertLess(abs(F(1.,-1.,t0-1e-10,.4,q)-F(1.,-1.,t0+1e-10,.4,q)),1e-8)
 def test_near_zero_no_forced_reset(self):self.assertNotEqual(F(1e-12,0,.05,.4,.5),0.)
 def test_subnormal_target(self):self.assertTrue(math.isfinite(F(1.,-5e-324,.05,.4,.5)))
 def test_bounded_endpoints(self):
  rng=random.Random(351)
  for _ in range(2000):
   x,r=rng.uniform(-3,3),rng.uniform(-3,3);v=F(x,r,rng.random()*.2,.39276,rng.choice((.5,2.)))
   self.assertGreaterEqual(v,min(x,r)-1e-14);self.assertLessEqual(v,max(x,r)+1e-14)
 def test_semigroup(self):
  rng=random.Random(352)
  for _ in range(2000):
   x,r=rng.uniform(-2,2),rng.uniform(-2,2);q=rng.choice((.5,2.));h=rng.uniform(0,.2)
   self.assertAlmostEqual(F(F(x,r,h/2,.4,q),r,h/2,.4,q),F(x,r,h,.4,q),12)
 def test_independent_ode(self):
  from scipy.integrate import solve_ivp
  for x,r in ((1,-1),(-1,1),(1,.2),(-1,-.2),(0,1)):
   for q in (.5,2.):
    def rhs(t,z):
     a=z[0];tau=.4*q if a*(r-a)<0 else .4
     return [(r-a)/tau]
    sol=solve_ivp(rhs,[0,.19],[x],rtol=1e-11,atol=1e-12,max_step=.0005)
    self.assertLess(abs(float(sol.y[0,-1])-F(x,r,.19,.4,q)),1e-10)
 def test_stale_exact_local_drive(self):
  for q in (.5,2.):
   a,b=build(),build(q);a.reset(velocity=5);b.reset(velocity=5);a.drive_a=b.drive_a=.8
   for k in range(100):
    t=k*.05;ea=a.step(t);eb=b.step(t)
    self.assertEqual(norm(ea),norm(eb))
 def test_future_invalid_command(self):
  for cmd in (Sample(10.,.8),Sample(0.,float('nan')),Sample(0.,2.)):
   a,b=build(),build(.5);a.reset(velocity=4);b.reset(velocity=4);a.drive_a=b.drive_a=1.
   self.assertEqual(norm(a.step(0.,cmd)),norm(b.step(0.,cmd)))
 def test_off_all_states(self):
  a,b=build(),build(1.);rng=random.Random(353)
  for k in range(8000):
   t=k*.05;v=5+.5*math.sin(t*.2);u=.8*math.sin(t*.7)
   f=Sample(t,v) if k%2==0 else None;r=Sample(t,v) if k%2==0 else None
   if 50<k%200<80:f=r=None
   if 120<k%200<135:f=r=Sample(t,0.)
   if k%200 in (151,152):f=r=Sample(t,15.)
   ea=a.step(t,Sample(t,u),f,r);eb=b.step(t,Sample(t,u),f,r)
   self.assertEqual(norm(ea),norm(eb))
   for name,val in vars(a).items():self.assertEqual(norm(val),norm(getattr(b,name)),name)
 def test_causal_prefix_and_duplicates(self):
  for q in (.5,2.):
   a,b=build(q),build(q)
   for k in range(300):
    t=k*.05;stamp=math.floor(k/2)*.1;cmd=Sample(t,.6 if t<4 else 0);w=Sample(stamp,5.)
    self.assertEqual(norm(a.step(t,cmd,w,w)),norm(b.step(t,cmd,w,w)))
   prefix=norm(a.last_estimate);b.step(15.,Sample(15.,-1),Sample(15.,4),Sample(15.,4))
   self.assertEqual(norm(a.last_estimate),prefix)
 def test_reset_exact(self):
  a=build(.5);a.step(0,Sample(0,1),Sample(0,3),Sample(0,3));a.reset()
  b=build(.5);self.assertEqual(norm(vars(a)),norm(vars(b)))
 def test_bounded_state(self):
  a=build(2.);keys=set(vars(a))
  for k in range(10000):
   t=k*.05;e=a.step(t,Sample(t,math.sin(t)),Sample(t,4),Sample(t,4))
   self.assertEqual(set(vars(a)),keys);self.assertTrue(all(math.isfinite(getattr(e,x)) for x in ('s','v','a','disturbance')))
 def test_zero_lock_and_true_stop(self):
  for q in (.5,2.):
   a=build(q);a.reset(velocity=1.5)
   for k in range(10):
    t=k*.05;e=a.step(t,Sample(t,0),Sample(t,0),Sample(t,0));self.assertNotEqual(e.mode,'STOPPED')
   a.reset(velocity=0.)
   for k in range(30):t=k*.05;e=a.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
   self.assertEqual(e.mode,'STOPPED')
 def test_quarantine(self):
  a=build(.5);a.reset(velocity=3.)
  a.step(0,Sample(0,0),Sample(0,3),Sample(0,3))
  a.step(.05,Sample(.05,0),Sample(.05,8),Sample(.05,8))
  self.assertGreater(a.reacquire_blocked_until,1.)
 def test_distance_integral(self):
  for q in (.5,2.):
   a=build(q);old=None
   for k in range(500):
    t=k*.05;e=a.step(t,Sample(t,math.sin(t)),Sample(t,4),Sample(t,4))
    if old and e.mode not in ('INITIALIZED','WAITING_FOR_INITIALIZATION'):
     self.assertAlmostEqual(e.s-old.s,.5*(old.v+e.v)*(e.t-old.t),10)
    old=e
 def test_loss_before_after_release(self):
  for q in (.5,2.):
   for start in (3.8,4.2):
    a=build(q)
    for k in range(240):
     t=k*.05;w=None if start<=t<start+5 else Sample(t,4.)
     e=a.step(t,Sample(t,.7 if t<4 else 0),w,w)
     self.assertTrue(math.isfinite(e.s));self.assertTrue(math.isfinite(e.v))
 def test_branch_oracle_no_false_transitions(self):
  rng=random.Random(354)
  for _ in range(3000):
   x,r=rng.uniform(-2,2),rng.uniform(-2,2)
   self.assertEqual(runtime.release_phase(x,r),x*(r-x)<0)
if __name__=='__main__':unittest.main()
