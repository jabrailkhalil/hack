import json
import math
from pathlib import Path
import random
import sys
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools/research_R3_H24'),str(ROOT/'src/reserve_odometry')]
from common import profile, GuardedReadoutObserver, Sample, integrity
from reserve_odometry.command_map import CommandMap, CommandMapObserver
from reserve_odometry.core import Observer


def make(enabled=True, values=None):
    c,r,_=profile(); q=tuple(x**c.command_exponent for x in (.25,.5,.75))
    if values is None:values=q+q
    return CommandMapObserver(c,readout=r,command_map=CommandMap(values[:3],values[3:],enabled))


class CommandMapTests(unittest.TestCase):
    def test_profile_and_integrity(self):
        self.assertGreater(len(integrity()),30)
        c,r,ops=profile();self.assertEqual(c.common_mode_quarantine_s,1.5)
        self.assertEqual(r.gain,1.);self.assertEqual(ops['alignment_delay_s'],0.)

    def test_invalid_map(self):
        for q in ((.3,.2,.8),(-.1,.3,.8),(.2,.3,1.1),(float('nan'),.4,.8),(.1,.3)):
            with self.assertRaises(ValueError):CommandMap(q,(.2,.5,.8))
        with self.assertRaises(ValueError):CommandMap((.2,.5,.8),(.2,.5,.8),1)

    def test_inputs_immutable(self):
        q=[.2,.5,.8];m=CommandMap(q,q);q[0]=1
        self.assertEqual(m.traction,(.2,.5,.8))
        with self.assertRaises(Exception):m.traction=(.3,.5,.8)

    def test_endpoints_and_clamping(self):
        m=make().command_map
        for s in (True,False):
            self.assertEqual(m.value(0,s),0);self.assertEqual(m.value(1,s),1)
            self.assertEqual(m.value(-1,s),0);self.assertEqual(m.value(2,s),1)
        with self.assertRaises(ValueError):m.value(float('nan'),True)

    def test_monotone_bounds_random_maps(self):
        rng=random.Random(24)
        for _ in range(25):
            m=CommandMap(sorted(rng.random() for _ in range(3)),sorted(rng.random() for _ in range(3)))
            for side in (True,False):
                vals=[m.value(i/2000,side) for i in range(2001)]
                self.assertTrue(all(0<=x<=1 for x in vals))
                self.assertTrue(all(a<=b+1e-15 for a,b in zip(vals,vals[1:])))

    def test_continuity_knots(self):
        m=make().command_map
        for side in (True,False):
            for x in (.25,.5,.75):
                self.assertLessEqual(abs(m.value(x-1e-10,side)-m.value(x+1e-10,side)),8.1e-10)

    def test_near_deadband_and_sign(self):
        o=make()
        for u in (-.04,0,.04):self.assertEqual(o.drive_target(u,5),0)
        self.assertLess(abs(o.drive_target(.04+1e-10,5)),1e-8)
        self.assertGreater(o.drive_target(.5,5),0)
        self.assertLess(o.drive_target(-.5,5),0)
        self.assertGreater(o.drive_target(-.5,-5),0)
        self.assertEqual(o.drive_target(-.5,0),0)

    def test_torque_power_crossover_and_bound(self):
        o=make();c=o.c;f=c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m
        v=c.max_power_w/f
        self.assertAlmostEqual(o.drive_target(.6,v-1e-9),o.drive_target(.6,v+1e-9),places=8)
        for u in (-1,-.4,0,.4,1):
            for speed in (-30,-1,0,1,30):
                self.assertLessEqual(abs(o.drive_target(u,speed)),max(f,c.max_brake_force_n)/c.mass_kg)

    def test_off_uses_exact_power_not_prior_table(self):
        off=make(False);on=make();c,r,_=profile();base=GuardedReadoutObserver(c,readout=r)
        for i in range(-100,101):
            u=i/100
            self.assertEqual(off.drive_target(u,4),base.drive_target(u,4))
        self.assertNotEqual(on.drive_target(1/15,4),base.drive_target(1/15,4))

    def test_scope_inheritance(self):
        self.assertIs(CommandMapObserver.step,GuardedReadoutObserver.step)
        for m in ('_wheel','_reacquire_pair','_take_pending_pair','resistance','_valid'):
            self.assertIs(getattr(CommandMapObserver,m),getattr(Observer,m))

    def test_off_complete_v8_equivalence_6000_ticks(self):
        c,r,_=profile();a=GuardedReadoutObserver(c,readout=r);b=make(False);rng=random.Random(24)
        for i in range(6000):
            t=i*.05; ts=(i//2)*.1;u=math.sin(t*.4);v=4+math.sin(ts*.2)
            f=Sample(ts,v);rr=Sample(ts,v)
            if 300<i%1000<400:f=rr=None
            if 500<i%1000<510:f=rr=Sample(ts,v+5)
            if 600<i%1000<610:f=Sample(t+1,10)
            if i%997==0:a.reset();b.reset()
            inputs=(t,Sample(ts,u),f,rr)
            self.assertEqual(a.step(*inputs),b.step(*inputs))
            self.assertEqual(vars(a),{k:v for k,v in vars(b).items() if k!='command_map'})

    def test_prefix_causal_and_future(self):
        a=make();b=make()
        for i in range(400):
            t=i*.05;z=3+math.sin(t*.1);ts=(i//2)*.1
            f=Sample(ts,z) if i<200 else Sample(t+1,100)
            g=f if i<200 else Sample(t+1,-100)
            self.assertEqual(a.step(t,Sample(ts,.4),f,f),b.step(t,Sample(ts,.4),g,g))
        self.assertNotIn('ACCEPTED',(a.last_estimate.front_status,a.last_estimate.rear_status))

    def test_held_samples_not_reassimilated(self):
        o=make();s=Sample(0,4);o.step(0,Sample(0,0),s,s)
        o.step(.05,Sample(0,0),s,s)
        self.assertEqual(o.last_estimate.front_status,'DUPLICATE_OR_OLD')
        self.assertEqual(o.used,[0,0])

    def test_stale_command_equals_neutral(self):
        a=make();b=make();a.reset(velocity=5);b.reset(velocity=5)
        for i in range(20):
            t=i*.05
            self.assertEqual(a.step(t,Sample(-1,1)),b.step(t,None))

    def test_zero_lock_moving(self):
        o=make();o.reset(velocity=1.5)
        for i in range(40):
            t=i*.05;e=o.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
            self.assertNotIn(e.mode,('STOPPED','REACQUIRING'))
        self.assertGreater(e.v,1.)

    def test_quarantine_retained(self):
        o=make()
        for i in range(25):
            t=i*.1;z=5 if i<10 else 10;e=o.step(t,Sample(t,.5),Sample(t,z),Sample(t,z))
            if i>=10:self.assertNotEqual(e.mode,'REACQUIRING')
        self.assertGreaterEqual(o.reacquire_blocked_until,2.5)

    def test_real_stationary(self):
        o=make()
        for i in range(100):
            t=i*.05;e=o.step(t,Sample(t,-.5),Sample(t,0),Sample(t,0))
        self.assertEqual((e.mode,e.s,e.v),('STOPPED',0.,0.))

    def test_distance_consistent_and_bound_state(self):
        o=make();prev=None;names=None
        for i in range(12000):
            t=i*.05;ts=(i//2)*.1;z=3+math.sin(ts*.2)
            e=o.step(t,Sample(ts,.3),Sample(ts,z),Sample(ts,z))
            if names is None:names=set(vars(o))
            self.assertEqual(names,set(vars(o)))
            self.assertEqual(len(o.command_map.traction),3)
            self.assertTrue(all(math.isfinite(x) for x in (e.v,e.s,e.a,e.disturbance)))
            self.assertLessEqual(abs(e.v),o.c.max_speed_mps)
            self.assertLessEqual(abs(e.disturbance),o.c.disturbance_limit_mps2)
            if prev and e.mode!='INITIALIZED':
                self.assertAlmostEqual(e.s-prev.s,.5*(prev.v+e.v)*(e.t-prev.t),places=9)
            prev=e

    def test_reset_gap_invalid_time(self):
        o=make();o.step(0)
        for t in (-1,0,1,float('nan')):
            with self.assertRaises(ValueError):o.step(t)
        o.reset(position=2);self.assertEqual(o.s,2);self.assertEqual(o.disturbance,0)
        self.assertEqual(o._distance_correction,0);self.assertEqual(o.rate_anomaly_times,[None,None])


if __name__=='__main__':unittest.main()
