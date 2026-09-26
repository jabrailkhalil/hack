import dataclasses,math,random,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import common as cm
import factory as f

S=cm.Sample

def neutral(x):
    if dataclasses.is_dataclass(x):return dataclasses.asdict(x)
    if isinstance(x,(list,tuple)):return [neutral(v) for v in x]
    if isinstance(x,dict):return {k:neutral(v) for k,v in x.items()}
    return x

class H40(unittest.TestCase):
    def test_source_exact(self):cm.verify()
    def test_budget(self):self.assertEqual(len(f.sources()),2)
    def test_disabled_all_state(self):
        a,b=cm.baseline(),f.candidate(False)
        for i in range(1200):
            t=i*.05;u=.3 if i<400 else (-.15 if i<700 else 0.)
            z=max(0.,.4+1.2*math.sin(t/15))
            s=(S(t,u),S(t,z),S(t,z)) if i%2==0 else (S(t,u),None,None)
            ea,eb=a.step(t,*s),b.step(t,*s)
            self.assertEqual(neutral(ea),neutral(eb))
            for k,v in vars(a).items():self.assertEqual(neutral(v),neutral(getattr(b,k)),k)
    def test_energy(self):
        c=cm.profile()[0];c.quadratic_drag_n_s2_m2=0
        for v in [-39.,-1.,-.1,-1e-8,0.,1e-8,.1,1.,39.]:
            for dt in [1e-20,1e-12,.001,.05,.2]:
                _,p=f.prediction(c,v,dt,0.,0.)
                self.assertLessEqual(p*p,v*v+1e-16);self.assertGreaterEqual(p*v,0.)
    def test_prox_oracle(self):
        c=cm.profile()[0];rng=random.Random(40)
        for _ in range(10000):
            v=rng.uniform(-1,1);dt=10**rng.uniform(-9,-.7);drive=rng.uniform(-2,2);d=rng.uniform(-.6,.6)
            a,p=f.prediction(c,v,dt,drive,d)
            free=v+dt*(drive+d-c.quadratic_drag_n_s2_m2*v*abs(v)/c.mass_kg)
            expected=math.copysign(max(abs(free)-dt*c.rolling_force_n/c.mass_kg,0.),free)
            expected=max(v-dt*c.max_accel_mps2,min(v+dt*c.max_accel_mps2,expected))
            self.assertAlmostEqual(p,expected,places=13)
    def test_force_thresholds(self):
        c=cm.profile()[0];r=c.rolling_force_n/c.mass_kg
        for sign in (-1,1):
            for factor in (0.,.5,1.,1.001,2.):
                a,p=f.prediction(c,0.,.05,sign*factor*r,0.)
                self.assertAlmostEqual(p,sign*.05*max(factor*r-r,0.),places=15)
    def test_tiny_dt(self):
        c=cm.profile()[0]
        for dt in (1e-20,1e-15,1e-9):
            a,v=f.prediction(c,.1,dt,1.,0.)
            self.assertTrue(math.isfinite(a));self.assertTrue(math.isfinite(v));self.assertLessEqual(abs(a),3.)
    def test_invalid_predictor(self):
        c=cm.profile()[0]
        for x in (float('nan'),float('inf')):
            with self.assertRaises(ValueError):f.prediction(c,x,.05,0,0)
        with self.assertRaises(ValueError):f.prediction(c,0.,-.05,0.,0.)
    def test_dt_zero(self):self.assertEqual(f.prediction(cm.profile()[0],.1,0,0,0),(0.,.1))
    def test_bounds(self):
        c=cm.profile()[0]
        for v in (-40.,40.):
            for drive in (-100.,100.):
                a,p=f.prediction(c,v,.05,drive,0.);self.assertLessEqual(abs(a),3.);self.assertLessEqual(abs(p),40.)
    def test_model_zero_is_not_stopped(self):
        o=f.candidate();o.reset(velocity=.0001);o.step(0,S(0,0));e=o.step(.05,S(.05,0))
        self.assertEqual(e.v,0);self.assertEqual(e.mode,'MODEL_ONLY')
    def test_true_stop_dwell(self):
        o=f.candidate();o.step(0,S(0,0),S(0,0),S(0,0))
        for i in range(1,10):self.assertNotEqual(o.step(i*.05,S(i*.05,0),S(i*.05,0),S(i*.05,0)).mode,'STOPPED')
        self.assertEqual(o.step(.6,S(.6,0),S(.6,0),S(.6,0)).mode,'STOPPED')
    def test_low_speed_lock(self):
        o=f.candidate();o.step(0,S(0,.1),S(0,1.5),S(0,1.5))
        for i in range(1,60):
            t=i*.05;e=o.step(t,S(t,0),S(t,0),S(t,0));self.assertNotEqual(e.mode,'STOPPED')
    def test_quarantine(self):
        o=f.candidate();o.step(0,S(0,0),S(0,4),S(0,4));o.step(.1,S(.1,0),S(.1,9),S(.1,9))
        self.assertAlmostEqual(o.reacquire_blocked_until,1.6)
    def test_slow_roll(self):
        for v in (.08,.15,-.08):
            o=f.candidate()
            for i in range(100):
                t=i*.05;e=o.step(t,S(t,0),S(t,v),S(t,v))
                self.assertNotEqual(e.mode,'STOPPED');self.assertGreater(e.v*v,0)
    def test_start_and_brake(self):
        o=f.candidate()
        for i in range(240):
            t=i*.05;v=max(0.,min(t*.2,(12-t)*.2));u=.2 if t<6 else -.1
            e=o.step(t,S(t,u),S(t,v),S(t,v));self.assertTrue(math.isfinite(e.v))
            if v>.1:self.assertNotEqual(e.mode,'STOPPED')
    def test_load_on_outage(self):
        for d in (-.2,.2):
            o=f.candidate();o.reset(velocity=.4);o.disturbance=d
            for i in range(30):
                e=o.step(i*.05,S(i*.05,0));self.assertNotEqual(e.mode,'STOPPED');self.assertGreaterEqual(e.v,0)
    def test_future_rejected(self):
        o=f.candidate();e=o.step(0,S(1,.1),S(1,1),S(1,1));self.assertEqual(e.mode,'WAITING_FOR_INITIALIZATION')
    def test_duplicates(self):
        o=f.candidate();s=S(0,1);o.step(0,S(0,0),s,s);o.step(.05,S(.05,0),s,s)
        self.assertEqual(o.last_estimate.front_status,'DUPLICATE_OR_OLD')
    def test_stale(self):
        o=f.candidate();o.reset(velocity=1)
        e=o.step(1,S(0,0),S(0,1),S(0,1));self.assertTrue(e.command_stale)
    def test_causal_prefix(self):
        def replay(n):
            o=f.candidate();return [neutral(o.step(i*.05,S(i*.05,.1),S(i*.05,.2),S(i*.05,.2))) for i in range(n)]
        self.assertEqual(replay(30),replay(50)[:30])
    def test_reset(self):
        o=f.candidate();o.step(0,S(0,0),S(0,1),S(0,1));o.reset()
        self.assertEqual(neutral(vars(o)),neutral(vars(f.candidate())))
    def test_bounded_state(self):
        o=f.candidate();n=set(vars(o))
        for i in range(5000):o.step(i*.05,S(i*.05,.1),S(i*.05,.2),S(i*.05,.2))
        self.assertEqual(set(vars(o)),n)
    def test_published_integral(self):
        o=f.candidate();last=None
        for i in range(300):
            t=i*.05;v=max(.08,.3+.2*math.sin(t));e=o.step(t,S(t,.1),S(t-.01,v),S(t-.01,v))
            if last:self.assertAlmostEqual(e.s-last.s,.5*(last.v+e.v)*(e.t-last.t),places=12)
            last=e
    def test_readout_acceleration_consistency(self):
        class Trace(f.CoulombObserver):
            def _h40_prediction(self,*args):
                x=super()._h40_prediction(*args);self.calls.append((args,x));return x
        c,r=cm.profile();o=Trace(c,readout=r);o.calls=[];twice=0
        for i in range(100):
            o.calls=[];t=i*.05;o.step(t,S(t,.1),S(t-.01,.2),S(t-.01,.2))
            if len(o.calls)==2:self.assertEqual(o.calls[0],o.calls[1]);twice+=1
        self.assertGreater(twice,20)

if __name__=='__main__':unittest.main()
