import math
import random
import sys
import unittest
from dataclasses import asdict
from pathlib import Path
import build
from checks import AuditedCandidate, Candidate, CandidateConfig, Baseline, equal
from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.timeline import Timeline


def stream(n=700, offset=0):
    rng=random.Random(1207+offset)
    held=[None,None]
    for i in range(n):
        t=i*.05
        u=.4 if i%160<80 else -.2
        v=3.+.08*math.sin(t)
        if i%2==0:
            age=(.02,.08,.15,.24)[(i//40)%4]
            skew=(0.,.04,.09)[(i//30)%3]
            held=[Sample(t-age,v+rng.uniform(-.001,.001)),Sample(t-max(0.,age-skew),v)]
        f,r=held
        if 6<t<7:f=r=None
        if 9<t<10:f=r=Sample(t-.05,0.)
        if 12<t<13:f=Sample(t+1,3.)
        if 14<t<15:r=Sample(t-1,3.)
        if 17<t<18:f=Sample(t,15.)
        yield (t,None if 20<t<21 else Sample(t,u),f,r)


class H12Tests(unittest.TestCase):
    def test_pinned_sources_and_effective_profile(self):
        self.assertEqual(build.verify()['baseline'],build.BASELINE)
        self.assertEqual(build.config().wheel_time_compensation,0)
    def test_parameter_validation(self):
        for bad in (1,0,'yes',None):
            with self.assertRaises(ValueError):CandidateConfig(integral_age=bad)
    def test_piecewise_overlaps(self):
        o=build.observer();o._model_segments.extend([(0.,.1,1.),(.1,.2,3.),(.2,.3,-1.)])
        self.assertAlmostEqual(o._integral_between(.05,.25),.30)
        self.assertIsNone(o._integral_between(-.01,.25))
        self.assertEqual(o._integral_between(.2,.2),0)
    def test_average_individual_not_mean_stamp(self):
        o=build.observer();o._model_segments.extend([(0.,.1,1.),(.1,.2,3.)])
        pair=[Sample(.05,3),Sample(.15,3)]
        self.assertAlmostEqual(o._age_increment(.2,pair,3.,.1),.25)
        self.assertAlmostEqual(o._integral_between(.1,.2),.3)
    def test_fallback_whole_update(self):
        o=build.observer();o._model_segments.append((.1,.2,3.))
        self.assertEqual(o._age_increment(.2,[Sample(.05,3),Sample(.15,3)],3.,.1),3.*.1)
    def test_constant_acceleration_exact(self):
        o=build.observer();o._model_segments.extend([(0.,.1,.3),(.1,.2,.3)])
        self.assertEqual(o._age_increment(.2,[Sample(.05,3),Sample(.15,3)],.3,.1),.3*.1)
    def test_identity_through_transitions_faults_age_skew(self):
        o=AuditedCandidate()
        for a in stream(1600):o.step(*a)
        self.assertGreater(o.audit_changed,0)
        self.assertGreater(o.audit_multisegment,0)
        self.assertEqual(o.audit_ticks,1600)
    def test_same_segment_full_estimate_exact(self):
        o=AuditedCandidate()
        for i in range(600):
            t=i*.05;s=Sample(t-.02,3.+.01*math.sin(t))
            e=o.step(t,Sample(t,.3),s,s)
            self.assertTrue(equal(e,o.reference.last_estimate))
        self.assertEqual(o.audit_changed,0)
    def test_prefix_causality(self):
        data=list(stream(700)); changed=data[:350]+[
            (t,Sample(t,-.9),None,None) for t,u,f,r in data[350:]]
        def run(xs):
            o=AuditedCandidate()
            return [o.step(*x) for x in xs]
        prefix=run(data[:350]); original=run(data); altered=run(changed)
        self.assertTrue(equal(prefix,original[:350]))
        self.assertTrue(equal(prefix,altered[:350]))
        self.assertTrue(any(not equal(x,y) for x,y in zip(original[350:],altered[350:])))
    def test_actual_core_acceleration_capture(self):
        o=build.observer();actual=[]
        def profiler(frame,event,arg):
            if event=='return' and frame.f_code is Observer.step.__code__:
                actual.append((frame.f_locals.get('a_model'),arg.mode))
        previous=sys.getprofile();sys.setprofile(profiler)
        try:
            for args in stream(450):
                e=o.step(*args)
                if e.mode not in ('INITIALIZED','WAITING_FOR_INITIALIZATION') and o._model_segments:
                    self.assertTrue(equal(o._model_segments[-1][2],actual[-1][0]))
        finally:sys.setprofile(previous)
        self.assertEqual(len(actual),450)
    def test_memory_count_and_time_limits(self):
        o=AuditedCandidate()
        for i in range(20000):
            t=i*.001;s=Sample(t-.2,3.)
            o.step(t,Sample(t,.3),s,s)
        self.assertEqual(len(o._model_segments),16)
        self.assertIsNone(o._integral_between(o.t-.24,o.t))
        self.assertGreater(o.audit_fallback,0)
    def test_reset_and_invalid_clock(self):
        o=AuditedCandidate()
        for a in stream(70):o.step(*a)
        self.assertTrue(o._model_segments)
        with self.assertRaises(ValueError):o.step(o.t)
        with self.assertRaises(ValueError):o.step(o.t+.5)
        o.reset(velocity=2.)
        self.assertEqual(len(o._model_segments),0)
        self.assertIsNone(o.t)
        o.step(0.,Sample(0,.1),Sample(0,2),Sample(0,2))
    def test_duplicates_future_stale(self):
        o=AuditedCandidate();o.reset(velocity=3)
        s=Sample(0,3);o.step(0,Sample(0,.1),s,s)
        e=o.step(.05,Sample(.05,.1),s,s)
        self.assertEqual(e.front_status,'DUPLICATE_OR_OLD')
        e=o.step(.1,Sample(.1,.1),Sample(.2,3),Sample(-1.,3))
        self.assertEqual(e.front_status,'MISSING_OR_STALE')
        self.assertEqual(e.rear_status,'MISSING_OR_STALE')
    def test_low_speed_zero_lock_unchanged(self):
        o=AuditedCandidate();o.reset(velocity=1.5)
        for i in range(30):
            t=i*.05;e=o.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
            self.assertNotEqual(e.mode,'STOPPED')
            self.assertEqual(o._velocity_correction,0)
    def test_bounded_no_sign_reversal(self):
        o=AuditedCandidate()
        for a in stream(700):
            e=o.step(*a)
            self.assertLessEqual(abs(e.v-o.v),o.c.max_accel_mps2*o.c.max_age_s+1e-12)
            self.assertGreaterEqual(e.v*o.v,0)
    def test_distance_acceleration_consistent(self):
        o=AuditedCandidate();previous=None
        for a in stream(700):
            e=o.step(*a)
            if previous is not None and e.mode!='INITIALIZED':
                dt=e.t-previous.t
                self.assertAlmostEqual(e.s-previous.s,.5*(e.v+previous.v)*dt,places=10)
                self.assertAlmostEqual(e.a,(e.v-previous.v)/dt,places=10)
            previous=e

if __name__=='__main__':unittest.main(verbosity=2)
