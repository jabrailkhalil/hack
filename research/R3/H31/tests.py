"""Executable H31 invariants and mandatory counterexamples; no dataset needed."""
import argparse
from copy import deepcopy
from dataclasses import asdict
import json
import math
from pathlib import Path
import random
import sys
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'src/reserve_odometry'),str(Path(__file__).parent)]
from probe import profile
from reserve_odometry.core import Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver
from reserve_odometry.prequential_outage import PrequentialOutageObserver, EnsembleConfig, CompletedScore


def make(enabled=True, equal=False):
    c,r=profile()
    return PrequentialOutageObserver(c,readout=r,ensemble=EnsembleConfig(enabled,equal))


def warm(o, end=20., u=.2):
    for i in range(round(end*20)+1):
        t=i*.05;tw=(i//2)*.1
        o.step(t,Sample(t,u),Sample(tw,5.),Sample(tw,5.))


def seeded():
    o=make();o.reset(velocity=5)
    o.step(10,Sample(10,0),Sample(10,5),Sample(10,5))
    o.command_epoch=(0,0.)
    o.base.drive_a=.2
    for k in (2,4,6):
        o.scores.append(CompletedScore(k,k+1,k+1.1,(2.,0.,1.)))
    # Most recent record age<4s at 10.05.
    return o


class Invariants(unittest.TestCase):
    def test_disabled_exact_and_enabled_inner_7000(self):
        c,r=profile();b=GuardedReadoutObserver(c,readout=r);off=make(False);on=make()
        rng=random.Random(3103)
        for i in range(7000):
            t=i*.05;cmd=Sample(t, .1 if i%300<200 else -.1)
            ts=(i//2)*.1
            if i%211<180:
                z=4+.01*math.sin(ts);f=Sample(ts,z);re=Sample(ts,z+.001)
            else:f=re=None
            if i%503==0:f=Sample(t+1,5.)
            e=b.step(t,cmd,f,re);x=off.step(t,cmd,f,re);y=on.step(t,cmd,f,re)
            self.assertEqual(e,x)
            self.assertEqual(vars(b),vars(off.base))
            self.assertEqual(vars(b),vars(on.base))
            self.assertTrue(all(math.isfinite(v) for v in (y.v,y.s,y.a)))

    def test_scores_finish_before_selection(self):
        o=make()
        for k in (1,3,5):o.scores.append(CompletedScore(k,k+1,k+1,(0,0,0)))
        self.assertFalse(o._weights(6)[1])
        self.assertTrue(o._weights(6.05)[1])
        self.assertLess(o._weights(6.05)[2],6.05)
        self.assertFalse(o._weights(30)[1])

    def test_normalized_convex_weights(self):
        for values in ((0,0,0),(4,0,4),(0,4,4),(4,4,4)):
            o=make()
            for k in (1,3,5):o.scores.append(CompletedScore(k,k+1,k+1,values))
            w,usable,_,_=o._weights(6.1)
            self.assertTrue(usable);self.assertAlmostEqual(sum(w),1)
            self.assertGreaterEqual(w[0],.25);self.assertTrue(all(0<=x<=1 for x in w))

    def test_equal_weight_control_not_selector(self):
        o=make(equal=True)
        for k in (1,3,5):o.scores.append(CompletedScore(k,k+1,k+1,(4,0,4)))
        self.assertEqual(o._weights(6.1)[0],(1/3,1/3,1/3))

    def test_no_score_from_duplicates_and_completion_horizon(self):
        o=make();warm(o)
        self.assertGreater(o.stats['completed'],3)
        for r in o.scores:
            self.assertLessEqual(r.horizon,r.completed)
            self.assertAlmostEqual(r.horizon-r.start,1.)
        n=o.stats['completed']
        for i in range(1,4):o.step(20+i*.05,Sample(20,0.2),Sample(20,5),Sample(20,5))
        self.assertEqual(n,o.stats['completed'])

    def test_endpoint_cannot_change_initial_forecast(self):
        a,b=make(),make();warm(a,6);warm(b,6)
        # Force a fresh launch, no model change; then vary only later wheel target.
        for o in (a,b):o.pending=None;o.next_launch=6.05
        a.step(6.1,Sample(6.1,.2),Sample(6.1,5),Sample(6.1,5))
        b.step(6.1,Sample(6.1,.2),Sample(6.1,5),Sample(6.1,5))
        initial=a.pending.velocity
        for i in range(1,12):
            t=6.1+i*.05
            a.step(t,Sample(t,.2),Sample(t,5),Sample(t,5))
            b.step(t,Sample(t,.2),Sample(t,5.01),Sample(t,5.01))
        self.assertEqual(a.pending.velocity,initial)
        self.assertEqual(b.pending.velocity,initial)
        self.assertEqual(vars(a.pending.physics),vars(b.pending.physics))

    def test_distance_survives_recovery(self):
        o=seeded();last=o.last_estimate;oldbase=o.base.last_estimate;dv=0.;ds=0.
        for i in range(1,31):
            t=10+i*.05;e=o.step(t,Sample(t,0))
            new=e.v-o.base.last_estimate.v
            ds+=.5*(dv+new)*.05;dv=new
            self.assertAlmostEqual(e.s-o.base.last_estimate.s,ds,places=11)
            self.assertAlmostEqual(e.a,o.base.last_estimate.a+(new-(last.v-oldbase.v))/.05,places=10)
            last=e;oldbase=o.base.last_estimate
        self.assertNotEqual(ds,0)
        e=o.step(11.55,Sample(11.55,0),Sample(11.55,5),Sample(11.55,5))
        ds+=dv*.025
        self.assertEqual(e.v,o.base.last_estimate.v)
        self.assertAlmostEqual(e.s-o.base.last_estimate.s,ds,places=11)
        self.assertNotEqual(o.delta_s,0)

    def test_score_weights_frozen_in_outage(self):
        o=seeded();snap=None
        for i in range(1,31):
            e=o.step(10+i*.05,Sample(10+i*.05,0))
            if snap is None:snap=(list(o.scores),o.outage.weights)
            self.assertEqual(list(o.scores),snap[0]);self.assertEqual(o.outage.weights,snap[1])

    def test_regime_change_at_loss_exact_fallback(self):
        for u in (.8,-.8):
            o=seeded()
            for i in range(1,61):
                t=10+i*.05;e=o.step(t,Sample(t,u))
                self.assertEqual(e.v,o.base.last_estimate.v)
                self.assertEqual(o.delta_v,0)

    def test_command_magnitude_change_same_regime_invalidates(self):
        o=make();warm(o)
        self.assertGreaterEqual(len(o.scores),3)
        e=o.step(20.05,Sample(20.05,.8))
        self.assertEqual(e.v,o.base.last_estimate.v);self.assertFalse(o.outage.usable)

    def test_false_common_pair_return_and_zero_lock_bypass(self):
        o=seeded()
        for i in range(1,20):o.step(10+i*.05,Sample(10+i*.05,0))
        e=o.step(11,Sample(11,0),Sample(11,10),Sample(11,10))
        self.assertEqual(e.v,o.base.last_estimate.v)
        self.assertEqual(o.delta_v,0)
        e=o.step(11.05,Sample(11.05,0),Sample(11.05,0),Sample(11.05,0))
        self.assertEqual(e.v,o.base.last_estimate.v)

    def test_quarantine_overrides_existing_correction(self):
        o=seeded();o.step(10.05,Sample(10.05,0))
        o.base.reacquire_blocked_until=15
        e=o.step(10.1,Sample(10.1,0))
        self.assertEqual(e.v,o.base.last_estimate.v)

    def test_future_and_stale_are_not_labels(self):
        o=make();warm(o);n=o.stats['completed']
        o.step(20.05,Sample(25,.3),Sample(25,7),Sample(25,7))
        self.assertEqual(len(o.scores),0)
        self.assertIsNone(o.pending)
        self.assertEqual(n,o.stats['completed'])

    def test_prefix_invariance(self):
        a,b=make(),make()
        for i in range(501):
            t=i*.05;args=(t,Sample(t,.1),Sample(t,5.),Sample(t,5.))
            self.assertEqual(a.step(*args),b.step(*args))
        history=deepcopy(a.scores)
        for i in range(501,521):
            t=i*.05;a.step(t,Sample(t,.1));b.step(t,Sample(t,.5),Sample(t,6),Sample(t,6))
        self.assertTrue(all(s.horizon<=25 for s in history))
        # Prefix outputs were compared before either suffix was supplied.

    def test_bounded_state_10000(self):
        o=make()
        keys=None
        for i in range(10000):
            t=i*.05;cmd=Sample(t,0)
            w=Sample(t,5+.001*math.sin(t)) if i%401<350 else None
            e=o.step(t,cmd,w,w)
            self.assertLessEqual(len(o.scores),8)
            self.assertEqual(len(o.stats),len(o.STATS))
            self.assertLessEqual(abs(e.v),o.c.max_speed_mps)
            self.assertLessEqual(abs(o.delta_v),o.c.disturbance_limit_mps2+1e-10)
            if keys is None:keys=set(vars(o))
            self.assertEqual(set(vars(o)),keys)
            for score in o.scores:self.assertEqual(len(score.losses),3)
        self.assertEqual(o.stats['limit_failures'],0)

    def test_rate_bounds_and_no_reverse_in_outage(self):
        o=seeded();prev=o.last_estimate
        for i in range(1,61):
            t=10+i*.05;e=o.step(t,Sample(t,0))
            self.assertLessEqual(abs(e.v-prev.v),o.c.max_accel_mps2*.05+1e-9)
            self.assertGreaterEqual(e.v,0);prev=e
        self.assertEqual(o.stats['limit_failures'],0)

    def test_explicit_reset_only_clears_distance(self):
        o=seeded();o.step(10.05,Sample(10.05,0));self.assertNotEqual(o.delta_s,0)
        o.reset(position=7.,velocity=2.)
        self.assertEqual(o.delta_s,0);self.assertEqual(len(o.scores),0);self.assertIsNone(o.pending)
        self.assertEqual(o.step(0).s,7.)

    def test_invalid_time_preserves_auxiliary_state(self):
        o=seeded();s=deepcopy(o.scores)
        for t in (10,9,100,float('nan')):
            with self.assertRaises(ValueError):o.step(t)
            self.assertEqual(o.scores,s)


def risk_probes():
    rows=[]
    for kind in ('command_acceleration','command_braking','hidden_load_positive','hidden_load_negative','false_return'):
        o=make();c,r=profile();b=GuardedReadoutObserver(c,readout=r)
        err_b=[];err_c=[];stops=[0,0];return_errors=[[],[]];effective=0
        for i in range(701):
            t=i*.05;u=.2
            if kind=='command_acceleration' and t>=20:u=.8
            if kind=='command_braking' and t>=20:u=-.8
            truth=5.
            if kind=='hidden_load_positive':truth=5+.6*min(max(t-20,0),5)
            if kind=='hidden_load_negative':truth=5-.6*min(max(t-20,0),5)
            # Commanded changes use simple clipped acceleration truth, not oracle inputs.
            if kind=='command_acceleration':truth=5+.6*min(max(t-20,0),5)
            if kind=='command_braking':truth=max(0,5-.8*max(t-20,0))
            z=truth+5 if kind=='false_return' and 25<=t<26.2 else truth
            w=None if 20<=t<25 else Sample((i//2)*.1,z)
            e=b.step(t,Sample(t,u),w,w);f=o.step(t,Sample(t,u),w,w)
            assert vars(o.base)==vars(b)
            if 20<=t<25:
                err_b.append((e.v-truth)**2);err_c.append((f.v-truth)**2)
                effective+=abs(f.v-e.v)>1e-6
            if truth>1:
                stops[0]+=e.mode=='STOPPED';stops[1]+=f.mode=='STOPPED'
            if 25<=t<35:
                return_errors[0].append(abs(e.v-truth)<.25);return_errors[1].append(abs(f.v-truth)<.25)
        rb=math.sqrt(sum(err_b)/len(err_b));rc=math.sqrt(sum(err_c)/len(err_c))
        recovered=[any(all(x[j:j+20]) for j in range(len(x)-19)) for x in return_errors]
        passed=rc<=rb*1.005+1e-12 and stops[1]<=stops[0] and not(recovered[0] and not recovered[1]) and o.stats['limit_failures']==0
        rows.append(dict(kind=kind,baseline_event_rmse=rb,candidate_event_rmse=rc,false_stops=stops,recovered=recovered,effective_ticks=effective,passed=passed))
    # Same preregistered counterexample families, with nonzero pre-outage
    # acceleration so the ensemble actually intervenes (steady fixtures above
    # can make all three predictions identical).
    for kind in ('active_history_hidden_load_positive','active_history_hidden_load_negative',
                 'active_history_command_acceleration','active_history_command_braking',
                 'active_history_false_return'):
        o=make();c,r=profile();b=GuardedReadoutObserver(c,readout=r)
        eb=[];ec=[];stops=[0,0];ret=[[],[]];effective=0;selected=0
        for i in range(701):
            t=i*.05;u=.2;acc=.12
            if t>=20:
                if 'hidden_load_positive' in kind:acc=.72
                if 'hidden_load_negative' in kind:acc=-.48
                if 'command_acceleration' in kind:u=.8;acc=.72
                if 'command_braking' in kind:u=-.8;acc=-.8
            def true_at(ts):
                a=.12
                if ts>=20:
                    if 'hidden_load_positive' in kind or 'command_acceleration' in kind:a=.72
                    if 'hidden_load_negative' in kind:a=-.48
                    if 'command_braking' in kind:a=-.8
                return max(0.,3+.12*min(ts,20)+a*max(0.,ts-20))
            truth=true_at(t);tw=(i//2)*.1;z=true_at(tw)
            if 'false_return' in kind and 25<=t<26.2:z+=5
            w=None if 20<=t<25 else Sample(tw,z)
            e=b.step(t,Sample(t,u),w,w);f=o.step(t,Sample(t,u),w,w)
            assert vars(o.base)==vars(b)
            if 20<=t<25:
                eb.append((e.v-truth)**2);ec.append((f.v-truth)**2)
                effective+=abs(f.v-e.v)>1e-6
            if truth>1:
                stops[0]+=e.mode=='STOPPED';stops[1]+=f.mode=='STOPPED'
            if 25<=t<35:
                ret[0].append(abs(e.v-truth)<.25);ret[1].append(abs(f.v-truth)<.25)
        rb=math.sqrt(sum(eb)/len(eb));rc=math.sqrt(sum(ec)/len(ec))
        recovered=[any(all(x[j:j+20]) for j in range(len(x)-19)) for x in ret]
        passed=rc<=rb*1.005+1e-12 and stops[1]<=stops[0] and not(recovered[0] and not recovered[1]) and o.stats['limit_failures']==0
        rows.append(dict(kind=kind,baseline_event_rmse=rb,candidate_event_rmse=rc,false_stops=stops,
                         recovered=recovered,effective_ticks=effective,selected_outages=o.stats['selected_outages'],passed=passed))
    return dict(cases=rows,passed=all(r['passed'] for r in rows),scope='synthetic counterexamples, not real-data accuracy')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--risk-output',type=Path);p.add_argument('-v',action='store_true');args=p.parse_args()
    result=unittest.TextTestRunner(verbosity=2 if args.v else 1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Invariants))
    risk=risk_probes();print(json.dumps(risk,indent=2))
    if args.risk_output:
        args.risk_output.parent.mkdir(parents=True,exist_ok=True);args.risk_output.write_text(json.dumps(risk,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
