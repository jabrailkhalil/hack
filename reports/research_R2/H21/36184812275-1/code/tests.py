"""H21 fixed numerical, causal, safety and compatibility checks; no dataset."""
import dataclasses
import json
import math
from pathlib import Path
import random
import sys
import unittest
from factory import ROOT, factories, normalize, assert_off, patch_text
sys.path.insert(0,str(ROOT/'src/reserve_odometry'))
from reserve_odometry.core import Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver

MAKE, MOD, TMP, DIR = factories()


def simulate(kind, scenario, seconds=14):
    """Synthetic truth explicitly separate from estimator, never an input flag."""
    truth=MAKE('baseline');o=MAKE(kind);v=5.;a=0.;front=rear=None
    errors=[];veto=[];records=[]
    for i in range(int(seconds*20)+1):
        t=i*.05
        u=-.6 if scenario=='true_stop' and t>2 else 0.1
        d=(.6 if scenario=='load_positive' else -.6) if t>3 and scenario.startswith('load_') else 0.
        if i:
            for _ in range(50):
                h=.001
                target=truth.drive_target(u,v)
                # Small-step truth simulation, not a source of estimator features.
                a+=(1-math.exp(-h/truth.c.actuator_tau_s))*(target-a)
                nv=v+h*max(-truth.c.max_accel_mps2,min(truth.c.max_accel_mps2,a-truth.resistance(v)+d))
                v=0. if u<=truth.c.command_deadband and v*nv<0 else nv
        if i%2==0:
            bias=min(3.,max(0.,1.5*(t-3))) if scenario=='common_drift' and 3<=t<7 else 0.
            z=v+bias
            front=rear=Sample(t,z)
        f,r=front,rear
        if scenario=='dropout' and 3<=t<10:f=r=None
        if scenario=='zero_lock' and 3<=t<6:f=r=Sample(t,0.)
        e=o.step(t,Sample(t,u),f,r)
        errors.append(abs(e.v-v));veto.append(len(getattr(o,'h21_rejections',())))
        records.append(dict(t=t,true_v=v,v=e.v,s=e.s,mode=e.mode,
            width=(o.h21_bounds[1]-o.h21_bounds[0]) if getattr(o,'h21_bounds',None) else None,
            veto=veto[-1]))
    return dict(max_error=max(errors),rmse=math.sqrt(sum(e*e for e in errors)/len(errors)),
                veto=sum(veto),counts=getattr(o,'h21_counts',{}),records=records)


class H21Tests(unittest.TestCase):
    def test_exact_disabled_7000_ticks(self):
        a,b=MAKE('baseline'),MAKE('off');rng=random.Random(2107)
        front=rear=None
        for i in range(7000):
            t=.05*i
            if i%2==0:
                z=4+math.sin(t*.1)
                front=Sample(t,z+(5 if 4<t%17<5 else 0))
                rear=Sample(t,z)
            cmd=Sample(t,.1 if i%600<300 else -.1)
            f=None if i%900<20 else front
            r=None if i%901<20 else rear
            ea=a.step(t,cmd,f,r);eb=b.step(t,cmd,f,r)
            self.assertEqual(normalize(ea),normalize(eb));assert_off(a,b)
        self.assertTrue(all(n==0 for n in b.h21_counts.values()))

    def test_target_bounds_full_interval_signed(self):
        rng=random.Random(2107);o=MAKE('candidate')
        for direction in (-1.,1.):
            o.c.travel_direction=direction
            for _ in range(200):
                lo,hi=sorted((rng.uniform(-40,40),rng.uniform(-40,40)))
                u=rng.uniform(-1,1);low,high=MOD.drive_bounds(o,u,lo,hi)
                for k in range(31):
                    v=lo+(hi-lo)*k/30;g=o.drive_target(u,v)
                    self.assertLessEqual(low-1e-12,g);self.assertLessEqual(g,high+1e-12)

    def test_propagation_contains_sampled_trajectories(self):
        rng=random.Random(2107);o=MAKE('candidate')
        for _ in range(160):
            v=rng.uniform(-25,25);u=rng.uniform(-1,1);dt=rng.uniform(.01,.2)
            dl,dh=MOD.physical_drive_bounds(o.c);a=rng.uniform(dl,dh)
            bounds=(v-.1,v+.1,dl,dh);result=MOD.propagate(o,bounds,dt,(u,u))
            d=rng.uniform(-.6,.6);h=dt/300
            for __ in range(300):
                target=o.drive_target(u,v);a+=(1-math.exp(-h/o.c.actuator_tau_s))*(target-a)
                v+=h*max(-3,min(3,a-o.resistance(v)+d))
            self.assertLessEqual(result[0]-1e-8,v);self.assertLessEqual(v,result[1]+1e-8)

    def test_uncertainty_widens_without_information(self):
        o=MAKE('candidate');dl,dh=MOD.physical_drive_bounds(o.c);b=(5.,5.1,dl,dh)
        width=b[1]-b[0]
        for _ in range(100):
            b=MOD.propagate(o,b,.05,None)
            self.assertGreaterEqual(b[1]-b[0],width-1e-10);width=b[1]-b[0]

    def test_veto_executes_then_releases(self):
        o=MAKE('candidate');o.reset(velocity=5.);o.t=0
        o.h21_bounds=(3.7,3.8,0.,0.);o.h21_anchor_t=0.;o.h21_active=True
        statuses=['CANDIDATE','CANDIDATE'];samples=[Sample(.05,5),Sample(.05,5)]
        kept=o._supervise_updates(.05,5.,samples,statuses,[0,1])
        self.assertEqual(kept,[]);self.assertEqual(o.h21_bounds,(3.7,3.8,0.,0.))
        kept=o._supervise_updates(.6,5.,[Sample(.6,5)]*2,['CANDIDATE']*2,[0,1])
        self.assertEqual(kept,[0,1]);self.assertIsNone(o.h21_bounds)

    def test_zero_and_strong_updates_untouched(self):
        o=MAKE('candidate');o.h21_active=True;o.h21_bounds=(4.,4.1,0.,0.)
        for z,p in ((0.,0.),(7.,5.)):
            ss=[Sample(1,z)]*2;statuses=['CANDIDATE']*2
            self.assertEqual(o._supervise_updates(1,p,ss,statuses,[0,1]),[0,1])

    def test_prefix_future_duplicate_and_reset(self):
        a,b=MAKE('candidate'),MAKE('candidate')
        for i in range(150):
            t=i*.05;cmd=Sample(t,.1);z=Sample((i//2)*.1,5.)
            self.assertEqual(normalize(a.step(t,cmd,z,z)),normalize(b.step(t,cmd,z,z)))
        before=normalize(a.last_estimate)
        a.step(7.5,Sample(100,1),Sample(100,30),Sample(100,30))
        self.assertEqual(before,normalize(b.last_estimate))
        self.assertEqual(a.used,b.used)
        eb=b.step(7.5,None,None,None)
        self.assertEqual(normalize(a.last_estimate),normalize(eb))
        a.reset();self.assertIsNone(a.h21_bounds);self.assertEqual(a.h21_counts['veto'],0)

    def test_invalid_times_do_not_mutate(self):
        o=MAKE('candidate');o.step(1.,Sample(1,0),Sample(1,4),Sample(1,4))
        old=normalize(vars(o))
        for t in (1.,0.,5.,float('nan')):
            with self.assertRaises(ValueError):o.step(t)
            self.assertEqual(old,normalize(vars(o)))

    def test_bounded_memory_nan_and_long_dropout(self):
        o=MAKE('candidate');keys=set(vars(o));o.reset(velocity=5.)
        for i in range(10000):
            t=i*.05;e=o.step(t,Sample(t,.1),Sample(t,float('nan')),None)
            self.assertTrue(all(math.isfinite(x) for x in (e.v,e.s,e.a)))
            self.assertEqual(set(vars(o)),keys)
            self.assertLessEqual(len(o.h21_rejections),2)
            self.assertTrue(o.h21_bounds is None or len(o.h21_bounds)==4)

    def test_safe_true_load_change_and_stop(self):
        for scenario in ('load_positive','load_negative','true_stop'):
            c=simulate('candidate',scenario)
            self.assertEqual(c['veto'],0,scenario)

    def test_existing_observer_scenarios_enabled(self):
        sys.path.insert(0,str(ROOT/'tests'))
        import test_core
        class FixedH21Tests(test_core.ObserverTests):
            pass
        # Existing test module imports are replaced only within this local test.
        old=test_core.Observer
        try:
            test_core.Observer=lambda config=None: MOD.ReachableIntervalObserver(config or MAKE('baseline').c)
            result=unittest.TestResult()
            unittest.defaultTestLoader.loadTestsFromTestCase(FixedH21Tests).run(result)
            self.assertEqual(result.errors,[]);self.assertEqual(result.failures,[])
        finally:test_core.Observer=old


if __name__=='__main__':
    if '--diagnostics' in sys.argv:
        output=Path(sys.argv[sys.argv.index('--diagnostics')+1]);output.mkdir(parents=True,exist_ok=False)
        data={scenario:{name:simulate(name,scenario) for name in ('baseline','candidate')}
              for scenario in ('load_positive','load_negative','true_stop','common_drift','dropout','zero_lock')}
        (output/'synthetic.json').write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
        print({s:{n:(v['rmse'],v['veto']) for n,v in ns.items()} for s,ns in data.items()})
    else:unittest.main()
