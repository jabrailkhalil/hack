"""Pre-development invariants; synthetic evidence is not an accuracy result."""
import math, random, unittest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from support import profile, baseline, Sample, Timeline, ROOT, Store
from factory import candidate, CommandEventTimeline, HOOK_PATCH, PATCHED_CORE


def state_equal(test, a, b):
    for key,value in vars(b).items():
        test.assertEqual(getattr(a,key),value,key)


def ready(enabled=True, velocity=4.):
    o=candidate(profile()[0],enabled)
    o.reset(velocity=velocity)
    o.step(0.,Sample(0.,0.),None,None)
    return o


def decay(o,d,u,dt,v):
    return d+(1-math.exp(-dt/o.c.actuator_tau_s))*(o.drive_target(u,v)-d)


class H32Tests(unittest.TestCase):
    def test_01_exact_profile(self):
        c,r=profile();self.assertEqual(c.common_mode_quarantine_s,1.5)
        self.assertEqual(c.adaptation_tau_s,.5);self.assertEqual(r.gain,1.)
    def test_02_hook_scope(self):
        self.assertEqual(sum(l.startswith('+') and not l.startswith('+++') for l in HOOK_PATCH.splitlines()),1)
        self.assertNotIn('GNSS',HOOK_PATCH)
    def test_03_feature_off_all_state(self):
        o=candidate(profile()[0],False);b=baseline();rng=random.Random(32)
        for k in range(6000):
            t=k*.05;u=Sample(t-.02,rng.choice([-.3,0.,.3]))
            f=Sample(t-.01,3.+.05*math.sin(t));r=f
            if 100<k%500<200:f=r=None
            a=o.step(t,u,f,r);z=b.step(t,u,f,r)
            self.assertEqual(a,z);state_equal(self,o,b)
    def test_04_constant_command_exact(self):
        for value in (-.4,0.,.4):
            o=candidate(profile()[0]);b=baseline()
            for k in range(2000):
                t=k*.05;s=Sample(t-.01,4.+.05*math.sin(t));u=Sample(t-.02,value)
                self.assertEqual(o.step(t,u,s,s),b.step(t,u,s,s));state_equal(self,o,b)
    def test_05_midstep_formula(self):
        o=ready();old=o.drive_a;v=o.v;u=Sample(.025,.5)
        expected=decay(o,decay(o,old,0.,.025,v),.5,.025,v)
        o.step(.05,u);self.assertEqual(o.drive_a,expected)
    def test_06_right_boundary_no_effect(self):
        o=ready();v=o.v;expected=decay(o,o.drive_a,0.,.05,v)
        o.step(.05,Sample(.05,.5));self.assertEqual(o.drive_a,expected)
    def test_07_left_boundary_full_effect(self):
        o=ready();o._predecessor=Sample(-.01,0.)
        v=o.v;expected=decay(o,o.drive_a,.5,.05,v)
        o.step(.05,Sample(0.,.5));self.assertEqual(o.drive_a,expected)
    def test_08_multiple_changes(self):
        o=ready();v=o.v;d=o.drive_a
        for t,u in ((.01,.5),(.03,-.2),(.045,.1)):o.receive_command(Sample(t,u))
        for h,u in ((.01,0.),(.02,.5),(.015,-.2),(.005,.1)):d=decay(o,d,u,h,v)
        o.step(.05,Sample(.045,.1));self.assertAlmostEqual(o.drive_a,d,15)
        self.assertEqual(o.h32_counts['events_applied'],3)
    def test_09_equal_refresh_arithmetic(self):
        o=ready();o.receive_command(Sample(.01,0.));o.receive_command(Sample(.03,0.))
        expected=decay(o,o.drive_a,0.,.05,o.v)
        o.step(.05,Sample(.045,0.));self.assertEqual(o.drive_a,expected)
    def test_10_impulse_near_left(self):
        o=ready();v=o.v;d=o.drive_a
        o.receive_command(Sample(1e-6,.5));o.receive_command(Sample(.049999,0.))
        d=decay(o,decay(o,decay(o,d,0.,1e-6,v),.5,.049998,v),0.,1e-6,v)
        o.step(.05,Sample(.049999,0.));self.assertAlmostEqual(o.drive_a,d,14)
    def test_11_impulse_near_right(self):
        o=ready();o.receive_command(Sample(.049999,.5));o.step(.05,Sample(.05,0.))
        self.assertGreater(o.drive_a,0.);self.assertLess(o.drive_a,1e-5)
    def test_12_future_does_not_act(self):
        a=ready();b=ready();a.receive_command(Sample(.4,.8))
        for k in range(1,7):
            t=k*.05;u=Sample(t,0.)
            self.assertEqual(a.step(t,u),b.step(t,u))
    def test_13_availability_no_rewrite(self):
        a=ready();saved=a.last_estimate
        a.receive_command(Sample(.025,.5))
        self.assertEqual(a.last_estimate,saved)
    def test_14_late_applies_next_step_only(self):
        o=ready();o.step(.05,Sample(0.,0.));saved=o.last_estimate
        u=Sample(.025,.5);o.receive_command(u);v=o.v
        expected=decay(o,o.drive_a,.5,.05,v)
        self.assertEqual(o.last_estimate,saved);o.step(.1,u)
        self.assertAlmostEqual(o.drive_a,expected,15)
    def test_15_stale_current_exact_legacy(self):
        o=ready();o.step(.2,Sample(0.,0.));o.step(.4,Sample(0.,0.));v=o.v
        expected=decay(o,o.drive_a,0.,.2,v)
        e=o.step(.6,Sample(0.,.5));self.assertEqual(o.drive_a,expected)
        self.assertTrue(e.command_stale);self.assertIsNone(o._predecessor)
    def test_16_missing_prior_fallback(self):
        o=ready();o._predecessor=None;v=o.v;expected=decay(o,o.drive_a,.5,.05,v)
        o.step(.05,Sample(.025,.5));self.assertEqual(o.drive_a,expected)
    def test_17_overflow_bound_and_fallback(self):
        o=ready()
        for k in range(40):o.receive_command(Sample(.001*(k+1),.2 if k%2 else .4))
        self.assertLessEqual(len(o._commands)+1,32);self.assertGreater(o.h32_counts['overflow_loss'],0)
        u=Sample(.04,.2);expected=decay(o,o.drive_a,.2,.05,o.v)
        o.step(.05,u);self.assertEqual(o.drive_a,expected)
        self.assertGreater(o.h32_counts['fallback_lost_history'],0)
    def test_18_future_overflow_prefix(self):
        a=ready();b=ready()
        for k in range(40):a.receive_command(Sample(.3+k*.004,.4))
        for k in range(1,5):
            t=k*.05;u=Sample(t-.02,.2 if k%2 else -.2)
            self.assertEqual(a.step(t,u),b.step(t,u))
    def test_19_future_horizon_prefix(self):
        a=ready();b=ready();a.receive_command(Sample(10.,1.))
        self.assertEqual(len(a._commands),0)
        for k in range(1,5):
            t=k*.05;u=Sample(t-.02,.2 if k%2 else -.2)
            self.assertEqual(a.step(t,u),b.step(t,u))
    def test_20_invalid_delivery(self):
        o=ready()
        for s in (Sample(math.nan,0.),Sample(0.,math.inf),Sample(.01,2.)):
            o.receive_command(s)
        self.assertFalse(o._commands)
    def test_21_duplicate_delivery(self):
        o=ready();o.receive_command(Sample(.02,.4));o.receive_command(Sample(.02,-.4))
        self.assertEqual(len(o._commands),1);self.assertEqual(o._commands[0].value,.4)
    def test_22_reset_clears(self):
        o=ready();o.receive_command(Sample(.03,.3));o.reset()
        self.assertEqual(o._commands,[]);self.assertIsNone(o._predecessor)
        self.assertEqual(o._lost_from,math.inf)
    def test_23_invalid_time_no_mutation(self):
        import copy
        o=ready();saved=copy.deepcopy(vars(o))
        for t in (0.,-.05,math.nan,.3):
            with self.assertRaises(ValueError):o.step(t,Sample(.01,.3))
            self.assertEqual(vars(o),saved)
    def test_24_timeline_off_exact(self):
        a=CommandEventTimeline(candidate(profile()[0],False),20.,0.)
        b=Timeline(baseline(),20.,0.)
        for k in range(1000):
            t=k*.031
            for ch,v in ((0,.3*math.sin(t)),(1,3.),(2,3.)):
                s=Sample(t,v);self.assertEqual(a.ingest(ch,s),b.ingest(ch,s))
                self.assertEqual(list(a.advance()),list(b.advance()))
        self.assertEqual(a.resets,b.resets);self.assertEqual(a.dropped,b.dropped)
    def test_25_seek(self):
        tl=CommandEventTimeline(candidate(profile()[0]),20.,0.)
        for ch,v in ((0,.4),(1,4.),(2,4.)):tl.ingest(ch,Sample(4.,v))
        list(tl.advance());tl.observer.receive_command(Sample(4.02,-.3))
        list(tl.advance(now=0.));self.assertEqual(tl.resets,1)
        self.assertEqual(tl.observer._commands,[])
    def test_26_zero_lock(self):
        o=ready(velocity=1.5)
        for k in range(1,61):
            t=k*.05;e=o.step(t,Sample(t,0.),Sample(t,0.),Sample(t,0.))
            self.assertNotEqual(e.mode,'STOPPED');self.assertGreater(e.v,.25)
    def test_27_common_quarantine(self):
        o=ready();o.step(.05,Sample(.05,0.),Sample(.05,4.),Sample(.05,4.))
        o.step(.1,Sample(.1,0.),Sample(.1,9.),Sample(.1,9.))
        self.assertGreaterEqual(o.reacquire_blocked_until,1.6)
        for k in range(3,20):
            t=k*.05;e=o.step(t,Sample(t,0.),Sample(t,9.),Sample(t,9.))
            self.assertNotEqual(e.mode,'REACQUIRING')
    def test_28_true_stop(self):
        o=ready(velocity=0.)
        for k in range(1,31):
            t=k*.05;e=o.step(t,Sample(t,0.),Sample(t,0.),Sample(t,0.))
        self.assertEqual(e.mode,'STOPPED');self.assertEqual(e.v,0.)
    def test_29_distance_derivative(self):
        o=ready();previous=o.last_estimate
        for k in range(1,1000):
            t=k*.05;s=Sample(t-.01,4.);e=o.step(t,Sample(t-.02,.2*math.sin(t)),s,s)
            self.assertAlmostEqual(e.s-previous.s,.5*(previous.v+e.v)*(e.t-previous.t),11)
            self.assertAlmostEqual(e.a,(e.v-previous.v)/(e.t-previous.t),10);previous=e
    def test_30_dense_bound(self):
        o=ready()
        for k in range(1,20001):
            t=k*.0001;o.step(t,Sample(t-.00001,.2 if k%2 else -.2))
            self.assertLessEqual(len(o._commands)+int(o._predecessor is not None),32)
        self.assertLessEqual(o.h32_max_commands,32)
    def test_31_role_isolation(self):
        store=Store('/tmp/h32-forbidden-access-journal.json')
        bag=store.plan['splits']['test'][0]
        with self.assertRaises(PermissionError):store.load(bag,'test')
    def test_32_direct_future_not_assimilated(self):
        a=ready();b=ready()
        self.assertEqual(a.step(.05,Sample(1.,1.)),b.step(.05,None))

if __name__=='__main__':unittest.main(verbosity=2)
