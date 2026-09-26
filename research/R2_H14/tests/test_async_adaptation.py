import copy
from dataclasses import asdict,is_dataclass
import math
from pathlib import Path
import random
import sys
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/research_R2_H14'))
from common import AsyncAdaptationObserver, GuardedReadoutObserver, Pristine, profile, manifest
from reserve_odometry.core import Sample
from reserve_odometry.timeline import Timeline


def normalized(x):
    if is_dataclass(x):return normalized(asdict(x))
    if isinstance(x,dict):return {k:normalized(v) for k,v in x.items() if not k.startswith('_h14')}
    if isinstance(x,(list,tuple)):return [normalized(v) for v in x]
    return x


def observer(cls=AsyncAdaptationObserver,**kwargs):
    c,r,_=profile();return cls(c,readout=r,**kwargs)


def stream(n=300,kind='async'):
    front=rear=None
    for k in range(n):
        t=k*.05;v=4+.2*t
        if k==0 or kind=='sync' or k%2==0: front=Sample(t,v)
        if k==0 or kind=='sync' or k%2==1: rear=Sample(t,v)
        yield t,Sample(t,.1),front,rear


class AsyncTests(unittest.TestCase):
    def test_applied_core_and_immutable_sources(self):
        self.assertTrue(manifest())

    def test_disabled_exact_pristine_all_state(self):
        a,b=observer(Pristine),observer(enabled=False)
        rng=random.Random(1401);front=rear=None
        for k in range(6000):
            t=k*.05;v=4+math.sin(t/4)
            if k%2==0:front=Sample(t,v+(5 if 80<k%300<90 else 0))
            if k%3==0:rear=Sample(t,v)
            if 100<k%300<115:front=rear=None
            cmd=Sample(t,rng.uniform(-.2,.3))
            self.assertEqual(asdict(a.step(t,cmd,front,rear)),asdict(b.step(t,cmd,front,rear)))
            self.assertEqual(normalized(vars(a)),normalized(vars(b)))

    def test_sync_exact_pristine_without_double_learning(self):
        a,b=observer(Pristine),observer()
        for data in stream(2000,'sync'):
            self.assertEqual(asdict(a.step(*data)),asdict(b.step(*data)))
            self.assertEqual(normalized(vars(a)),normalized(vars(b)))
        self.assertEqual(b._h14_counts['async_pairs'],0)
        self.assertLessEqual(b._h14_counts['updates'],b._h14_counts['pairs'])

    def test_async_activates_at_unique_pair_rate(self):
        a,b=observer(Pristine),observer(); seen=set();updates=0
        for data in stream(400):
            a.step(*data);b.step(*data)
            p=b._h14_last_pair
            if p:
                for ch,ts in enumerate(p[:2]):
                    self.assertNotIn((ch,ts),seen);seen.add((ch,ts))
                self.assertLessEqual(max(p[:2]),p[3]+1e-9)
            updates+=b._h14_updated
        self.assertGreater(b._h14_counts['async_updates'],100)
        self.assertEqual(updates,b._h14_counts['updates'])
        self.assertNotEqual(a.disturbance,b.disturbance)
        self.assertEqual(a.disturbance,0.)

    def test_hook_never_changes_velocity_or_covariance(self):
        o=observer();o.reset(velocity=5)
        for t,mode,samples,status in [(0.,'FUSED',[Sample(0,5),Sample(0,5)],['ACCEPTED']*2),
                   (.1,'SINGLE_WHEEL',[Sample(.1,5.02),None],['ACCEPTED','DUPLICATE_OR_OLD']),
                   (.15,'SINGLE_WHEEL',[None,Sample(.15,5.03)],['DUPLICATE_OR_OLD','ACCEPTED'])]:
            before=(o.v,o.s,o.pv,o.drive_a,o.sigma_s)
            o._adapt_disturbance(t,False,samples,status,mode,5.,3.)
            self.assertEqual(before,(o.v,o.s,o.pv,o.drive_a,o.sigma_s))
        self.assertEqual(o._h14_counts['async_updates'],1)

    def test_full_step_no_second_speed_update(self):
        o=observer();checks=0
        for data in stream(80):
            b=observer(GuardedReadoutObserver)
            for k,v in vars(o).items():
                if not k.startswith('_h14'):setattr(b,k,copy.deepcopy(v))
            eb=b.step(*data);eo=o.step(*data)
            if o._h14_updated:
                checks+=1
                for key in ('v','s','a','variance_v','variance_s','mode','front_status','rear_status'):
                    self.assertEqual(getattr(eb,key),getattr(eo,key))
        self.assertGreater(checks,10)

    def test_duplicate_pair_is_not_reused(self):
        o=observer();o.reset(velocity=5)
        for k in range(5):o.step(k*.05,Sample(k*.05,.1),Sample(0,5),Sample(0,5))
        self.assertLessEqual(o._h14_counts['pairs'],1)
        self.assertEqual(o._h14_counts['updates'],0)

    def test_hard_rejection_clears_pending_and_derivative(self):
        for status in ('RATE_ANOMALY','MODEL_DISAGREEMENT','ZERO_LOCK_SUSPECT','RANGE',
                       'AMBIGUOUS_PAIR','MISSING_OR_STALE'):
            o=observer();o.reset(velocity=5);o.disturbance=.2
            o._h14_pending=[Sample(0,5),None];o.adapt_previous=Sample(0,5)
            o._adapt_disturbance(.1,False,[None,Sample(.1,5)],
                                [status,'ACCEPTED'],'SINGLE_WHEEL',5.,3.)
            self.assertEqual(o._h14_pending,[None,None]);self.assertIsNone(o.adapt_previous)
            self.assertEqual(o.disturbance,.2)

    def test_accepted_pending_rechecked_against_current_model(self):
        o=observer();o.reset(velocity=5)
        o._adapt_disturbance(0,False,[Sample(0,5),None],['ACCEPTED','DUPLICATE_OR_OLD'],'SINGLE_WHEEL',5.,1.)
        o._adapt_disturbance(.05,False,[None,Sample(.05,5)],['DUPLICATE_OR_OLD','ACCEPTED'],'SINGLE_WHEEL',7.,1.)
        self.assertEqual(o._h14_counts['pairs'],0)
        self.assertEqual(o._h14_counts['recheck_rejections'],1)
        self.assertEqual(o._h14_pending,[None,None])

    def test_stale_pending_cannot_contaminate(self):
        o=observer();o.reset(velocity=5);o._h14_pending=[Sample(0,5),None]
        o.adapt_previous=Sample(0,5)
        o._adapt_disturbance(.3,False,[None,Sample(.3,5)],['DUPLICATE_OR_OLD','ACCEPTED'],'SINGLE_WHEEL',5.,3.)
        self.assertEqual(o._h14_counts['pairs'],0);self.assertIsNone(o.adapt_previous)
        self.assertIsNone(o._h14_pending[0])

    def test_excess_skew_drops_older(self):
        o=observer();o.reset(velocity=5);o._h14_pending=[Sample(0,5),None]
        o._adapt_disturbance(.11,False,[None,Sample(.11,5)],['DUPLICATE_OR_OLD','ACCEPTED'],'SINGLE_WHEEL',5.,3.)
        self.assertEqual(o._h14_counts['pairs'],0);self.assertIsNone(o._h14_pending[0])

    def test_pair_disagreement_rechecked(self):
        o=observer();o.reset(velocity=5);o._h14_pending=[Sample(0,4.5),None]
        o._adapt_disturbance(.05,False,[None,Sample(.05,5.5)],['DUPLICATE_OR_OLD','ACCEPTED'],'SINGLE_WHEEL',5.,3.)
        self.assertEqual(o._h14_counts['recheck_rejections'],1)

    def test_controller_stale_clears_without_training(self):
        o=observer();o.reset(velocity=5);o._h14_pending=[Sample(0,5),None]
        o._adapt_disturbance(.05,True,[None,Sample(.05,5)],['DUPLICATE_OR_OLD','ACCEPTED'],'SINGLE_WHEEL',5.,3.)
        self.assertEqual(o._h14_pending,[None,None]);self.assertEqual(o.disturbance,0.)

    def test_future_nonfinite_are_not_buffered(self):
        for s in (Sample(1,5),Sample(0,float('nan')),Sample(0,float('inf'))):
            o=observer();o.reset(velocity=5);o.step(0,Sample(0,0),s,Sample(0,5))
            self.assertEqual(o._h14_pending,[None,None]);self.assertEqual(o.disturbance,0.)

    def test_reset_gap_and_no_backward_pair_time(self):
        o=observer()
        for data in stream(20):o.step(*data)
        with self.assertRaises(ValueError):o.step(2.)
        o.reset();self.assertEqual(o._h14_pending,[None,None]);self.assertIsNone(o._h14_last_pair_t)
        ts=[]
        for data in stream(100):
            o.step(*data)
            if o._h14_last_pair:ts.append(o._h14_last_pair[2])
        self.assertTrue(all(y>x for x,y in zip(ts,ts[1:])))

    def test_prefix_causality(self):
        a,b=observer(),observer()
        left=list(stream(120));right=list(left)
        for i in range(70,120):
            t=right[i][0];right[i]=(t,Sample(t,-1),Sample(t,0),Sample(t,30))
        aa=[asdict(a.step(*d)) for d in left];bb=[asdict(b.step(*d)) for d in right]
        self.assertEqual(aa[:70],bb[:70])

    def test_low_speed_common_lock_not_stop(self):
        o=observer();o.step(0,Sample(0,0),Sample(0,1.5),Sample(0,1.5))
        for k in range(1,25):
            t=k*.05;e=o.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
            self.assertNotEqual(e.mode,'STOPPED');self.assertEqual(o.disturbance,0.)
            self.assertEqual(o._h14_pending,[None,None])

    def test_constant_memory_and_bounded_state(self):
        o=observer();keys=set(vars(o))
        for data in stream(12000):
            # Keep speeds in range over a long run.
            t,c,f,r=data;data=(t,c,Sample(f.t,4+.01*math.sin(f.t)),Sample(r.t,4+.01*math.sin(r.t)))
            e=o.step(*data)
            self.assertEqual(keys,set(vars(o)));self.assertEqual(len(o._h14_pending),2)
            self.assertEqual(len(o._h14_counts),7)
            self.assertTrue(math.isfinite(e.s));self.assertLessEqual(abs(e.disturbance),o.c.disturbance_limit_mps2)
            self.assertLessEqual(abs(e.v),o.c.max_speed_mps)

    def test_invalid_enabled(self):
        with self.assertRaises(ValueError):observer(enabled=1)

if __name__=='__main__':unittest.main()
