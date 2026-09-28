import copy, math, sys, unittest
from dataclasses import asdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import *
from reserve_odometry.traction_power import TractionPowerObserver as H37
from development import scored,full_audit,phase_metrics,windows

def make(enabled=True,**cfg):
    c,r=profile();return H37(Config(**(asdict(c)|cfg)),readout=r,enabled=enabled)

def stream(n=2000):
    held=[None,None];rows=[]
    for i in range(n):
        t=i*.05;u=.4 if i<500 else (0. if i<1000 else -.2)
        v=max(.1,10+.6*math.sin(t/3))
        if i%2==0:held=[Sample(t,v),Sample(t,v+.01)]
        f,r=held
        if 300<i<340 or 700<i<800:f=r=None
        if 400<i<430:f=r=Sample(t,v+5)
        if 900<i<940:f=r=Sample(t,0.)
        rows.append((t,Sample(t,u),f,r))
    return rows

class H37Tests(unittest.TestCase):
    def test_enabled_type(self):
        with self.assertRaises(ValueError):make(enabled=1)
    def test_q0_q1(self):
        o=make();b=baseline(o.c)
        for u in (0,.01,.04,1.):
            for v in (0,1,3,6,15,40,-40):self.assertEqual(o.drive_target(u,v),b.drive_target(u,v))
    def test_force_limited_exact(self):
        o=make();b=baseline(o.c)
        for u in np.linspace(0,1,99):
            for v in (0.,1.,3.,5.):self.assertEqual(o.drive_target(float(u),v),b.drive_target(float(u),v))
    def test_high_speed_small_command(self):
        o=make();b=baseline(o.c)
        self.assertGreater(o.drive_target(.1,15),b.drive_target(.1,15))
    def test_formula_and_bound(self):
        for direction in (-1.,1.):
            o=make(travel_direction=direction)
            for u in np.linspace(.04,1,71):
                for v in (0,1,3,6,10,20,40):
                    q,f,p,a,b=targets(o.c,float(u),v)
                    self.assertAlmostEqual(o.drive_target(float(u),v),b,14)
                    self.assertLessEqual(abs(b-a),f/(4*o.c.mass_kg)+1e-14)
    def test_continuity_monotonicity(self):
        o=make();q,f,p,_,_=targets(o.c,.4,15)
        q0=p/f;u0=o.c.command_deadband+(1-o.c.command_deadband)*q0**(1/o.c.command_exponent)
        self.assertAlmostEqual(o.drive_target(u0-1e-10,15),o.drive_target(u0+1e-10,15),8)
        y=[o.drive_target(float(u),15) for u in np.linspace(0,1,1001)]
        self.assertTrue(all(b>=a for a,b in zip(y,y[1:])))
    def test_braking_exact(self):
        o=make();b=baseline(o.c)
        for u in np.linspace(-1,0,81):
            for v in (-40.,-1.,0.,1.,12.,40.):self.assertEqual(o.drive_target(float(u),v),b.drive_target(float(u),v))
    def test_off_full_state(self):
        o=make(False);b=baseline(o.c)
        for args in stream():
            self.assertEqual(o.step(*args),b.step(*args))
            for k,v in vars(b).items():self.assertEqual(v,getattr(o,k),k)
    def test_prefix(self):
        a=make();b=make();rows=stream(800)
        first=[a.step(*x) for x in rows[:400]]
        whole=[b.step(*x) for x in rows]
        self.assertEqual(first,whole[:400])
    def test_stale_future_commands(self):
        for command in (Sample(-1,.5),Sample(.2,.5),Sample(0,float('nan')),Sample(0,2.)):
            a,b=make(),make()
            a.reset(velocity=10);b.reset(velocity=10)
            self.assertEqual(a.step(.1,command),b.step(.1,None))
    def test_future_wheels(self):
        a,b=make(),make();a.reset(velocity=10);b.reset(velocity=10)
        self.assertEqual(a.step(.1,None,Sample(.2,10),Sample(.2,10)),b.step(.1))
    def test_duplicate_not_reused(self):
        a=make();a.step(0,Sample(0,.4),Sample(0,10),Sample(0,10))
        e=a.step(.05,Sample(.05,.4),Sample(0,10),Sample(0,10))
        self.assertEqual((e.front_status,e.rear_status),('DUPLICATE_OR_OLD','DUPLICATE_OR_OLD'))
    def test_reset_and_bounds(self):
        a=make();keys=set(vars(a))
        for args in stream():
            e=a.step(*args)
            self.assertTrue(all(math.isfinite(x) for x in (e.v,e.s,e.disturbance,e.variance_v,e.variance_s)))
            self.assertLessEqual(abs(e.v),40);self.assertLessEqual(abs(e.disturbance),.6)
            self.assertEqual(set(vars(a)),keys)
        a.reset();self.assertEqual(vars(a),vars(make()))
    def test_bad_clock(self):
        a=make();a.step(0)
        for t in (0,-.1,1,float('nan')):
            with self.assertRaises(ValueError):a.step(t)
    def test_integral_recovery_and_stop(self):
        a=make();old=None
        for args in stream():
            e=a.step(*args)
            if old is not None and e.mode!='INITIALIZED':
                self.assertAlmostEqual(e.s-old.s,.5*(e.v+old.v)*(e.t-old.t),11)
            old=e
    def test_quarantine_and_lock(self):
        a=make();a.step(0,Sample(0,0),Sample(0,1.5),Sample(0,1.5))
        e=a.step(.1,Sample(.1,0),Sample(.1,6.5),Sample(.1,6.5))
        self.assertGreater(a.reacquire_blocked_until,1.5)
        self.assertEqual(e.mode,'MODEL_ONLY')
        b=make();b.step(0,Sample(0,0),Sample(0,1.5),Sample(0,1.5))
        for i in range(1,5):
            e=b.step(i*.05,Sample(i*.05,0),Sample(i*.05,0),Sample(i*.05,0))
            self.assertNotEqual(e.mode,'STOPPED')
    def test_original_methods_unmodified(self):
        self.assertIs(H37.step,GuardedReadoutObserver.step)
        self.assertIs(H37._wheel,GuardedReadoutObserver._wheel)
        self.assertIs(H37._reacquire_pair,GuardedReadoutObserver._reacquire_pair)
    def test_scorer_and_full_distance_synthetic(self):
        t=np.arange(0,65,.1);events=[]
        for x in t:
            events.extend([(x,0,.4 if x<35 else 0),(x,1,10.),(x,2,10.)])
        events=np.array(events);refs={'master':[(float(x),10.) for x in t],'rover':[]}
        result,arrays,_=scored(events,refs)
        self.assertEqual(result['receivers']['master']['R4_v8']['n'],result['receivers']['master']['H37']['n'])
        self.assertGreater(result['activation']['effective_output_ticks'],200)
        fault={'kind':'dropout','start':30.,'end':35.}
        f,a,_=scored(events,refs,fault);audit=full_audit(a,refs,fault)
        self.assertIsNotNone(audit['receivers']['master']['H37']['distance_surrogate']['reanchored_span_rmse_m'])
        self.assertIsNone(audit['receivers']['rover']['H37']['rmse'])
        self.assertIn('coast_first2s',phase_metrics(events,refs,arrays))
        self.assertTrue(any(s=='original' for s,_,_ in windows(events)))
if __name__=='__main__':unittest.main()
