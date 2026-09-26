"""Synthetic interface tests only. Fixture coefficients are NOT fitted results."""
from dataclasses import asdict
import inspect
import json
import math
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver
from runtime_profile import (BASELINE_SHA, PROFILE_SHA, ForceParameters,
                             baseline_configuration, make_observer, validate_artifact)
from calibration_spec import (ObjectiveBudget, joint_vectors, shrinkage_residuals,
                              soft_l1_residual, SHRINKAGE, MAX_RESIDUAL_CALLS)
from dependency_probe import probe


def synthetic_artifact():
    """Deliberately synthetic unit fixture, never exported as a research candidate."""
    return {'schema_version':'R5_H46_PARAMETERS_V1','hypothesis_id':'R5-H46',
            'baseline_sha':BASELINE_SHA,'baseline_profile_sha256':PROFILE_SHA,
            'status':'TRAIN_FIT_COMPLETE','mapping_status':'CONDITIONAL_ON_CONFIG',
            'dependencies_lock_sha256':'0'*64,'training_manifest_sha256':'1'*64,
            'global_parameters':asdict(ForceParameters(1.2,7.,1.1)),
            'vehicle_parameters':{'30618':asdict(ForceParameters(1.,6.,.9)),
                                  '30639':asdict(ForceParameters(1.4,8.,1.3))}}


def stream(n=2000):
    rng=random.Random(46)
    for i in range(n):
        t=i*.05;ts=(i//2)*.1
        u=.2 if i%600<300 else -.1
        z=3.0+.1*math.sin(ts)
        f=Sample(ts,z);r=Sample(ts,z)
        if 300<i%800<345:f=r=None
        if 500<i%800<508:f=r=Sample(ts,0.)
        if 510<i%800<524:f=r=Sample(ts,z+5.)
        if i%173==0:f=Sample(t+1,z)
        if i%179==0:r=Sample(ts,float('nan'))
        command=Sample(t-.8 if i%251==0 else ts,u)
        yield t,command,f,r


class ProfileTests(unittest.TestCase):
    def test_profile_complete_and_pinned(self):
        c,r,ops=baseline_configuration()
        self.assertEqual(set(asdict(c)),set(Config.__dataclass_fields__))
        self.assertEqual((ops['rate_hz'],ops['alignment_delay_s']),(20.,0.))
        self.assertEqual((r.gain,r.holdoff_s,c.common_mode_quarantine_s),(1.,.5,1.5))

    def test_profile_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.yaml';path.write_text('model.mass_kg: 42\n')
            with patch('runtime_profile.PROFILE',path),self.assertRaises(ValueError):
                baseline_configuration()

    def test_disabled_exact_state_and_estimate(self):
        c,r,_=baseline_configuration();base=GuardedReadoutObserver(c,readout=r)
        off,selection=make_observer(vehicle_profile='30618',enabled=False,artifact={})
        self.assertFalse(selection['active'])
        for args in stream():
            self.assertEqual(base.step(*args),off.step(*args))
            self.assertEqual(vars(base),vars(off))

    def test_unknown_exact_state_and_estimate(self):
        for label in (None,'unknown','30618_0652866c','/tmp/30639.db3','30618 ',30618):
            c,r,_=baseline_configuration();base=GuardedReadoutObserver(c,readout=r)
            fallback,meta=make_observer(vehicle_profile=label,enabled=True,artifact={'bad':object()})
            self.assertEqual(meta['reason'],'unknown_profile')
            for args in stream(300):
                self.assertEqual(base.step(*args),fallback.step(*args))
                self.assertEqual(vars(base),vars(fallback))

    def test_known_profile_without_artifact_fails(self):
        with self.assertRaises(ValueError): make_observer(vehicle_profile='30618',enabled=True)

    def test_incomplete_artifact_fails(self):
        fixture=synthetic_artifact();fixture['status']='NOT_FITTED'
        with self.assertRaises(ValueError):validate_artifact(fixture)

    def test_schema_rejects_per_bag_parameters(self):
        fixture=synthetic_artifact();fixture['vehicle_parameters']['30618_x']={}
        with self.assertRaises(ValueError):validate_artifact(fixture)
        fixture=synthetic_artifact();fixture['teacher_arrays']=[]
        with self.assertRaises(ValueError):validate_artifact(fixture)

    def test_provenance_required(self):
        for field in ('baseline_sha','baseline_profile_sha256','dependencies_lock_sha256','training_manifest_sha256'):
            fixture=synthetic_artifact();fixture[field]='bad'
            with self.assertRaises(ValueError):validate_artifact(fixture)

    def test_conditional_mapping_not_claimed_proven(self):
        fixture=synthetic_artifact();fixture['mapping_status']='AUTOMATICALLY_IDENTIFIED'
        with self.assertRaises(ValueError):validate_artifact(fixture)
        _,meta=make_observer(vehicle_profile='30618',enabled=True,artifact=synthetic_artifact())
        self.assertEqual(meta['mapping_status'],'CONDITIONAL_ON_CONFIG')

    def test_only_three_physical_fields_change(self):
        base,_,_=baseline_configuration()
        obj,_=make_observer(vehicle_profile='30618',enabled=True,artifact=synthetic_artifact())
        changed={k for k,v in asdict(base).items() if asdict(obj.c)[k]!=v}
        self.assertEqual(changed,{'total_motor_torque_nm','max_power_w','max_brake_force_n'})
        self.assertIs(type(obj),GuardedReadoutObserver)

    def test_baseline_roundtrip_exact(self):
        c,_,_=baseline_configuration()
        self.assertEqual(asdict(c),asdict(ForceParameters.from_config(c).apply(c)))

    def test_explicit_global_selection(self):
        obj,meta=make_observer(vehicle_profile='global',enabled=True,artifact=synthetic_artifact())
        self.assertEqual(meta['selected'],'global')
        self.assertAlmostEqual(ForceParameters.from_config(obj.c).power_per_mass,7.)

    def test_swapped_known_profile_is_not_silently_corrected(self):
        a,_=make_observer(vehicle_profile='30618',enabled=True,artifact=synthetic_artifact())
        b,_=make_observer(vehicle_profile='30639',enabled=True,artifact=synthetic_artifact())
        a.reset(velocity=5.);b.reset(velocity=5.)
        for i in range(100):
            t=i*.05;aa=a.step(t,Sample(t,.4));bb=b.step(t,Sample(t,.4))
        self.assertNotEqual(aa.v,bb.v)
        self.assertNotEqual(aa.s,bb.s)

    def test_no_extra_dynamic_state_or_runtime_inputs(self):
        c,r,_=baseline_configuration();base=GuardedReadoutObserver(c,readout=r)
        obj,_=make_observer(vehicle_profile='30618',enabled=True,artifact=synthetic_artifact())
        self.assertEqual(set(vars(obj)),set(vars(base)))
        self.assertEqual(inspect.signature(obj.step),inspect.signature(base.step))

    def test_prefix_reset_and_bounds_on_synthetic_profile(self):
        objs=[make_observer(vehicle_profile='30618',enabled=True,artifact=synthetic_artifact())[0] for _ in range(2)]
        for args in stream(1000):
            a,b=[o.step(*args) for o in objs]
            self.assertEqual(a,b)
            self.assertTrue(all(math.isfinite(x) for x in (a.v,a.s,a.disturbance)))
            self.assertLessEqual(abs(a.v),40.)
            self.assertLessEqual(abs(a.disturbance),.6)
        for obj in objs:obj.reset()
        self.assertEqual(vars(objs[0]),vars(objs[1]))

    def test_low_speed_zero_lock_guard_preserved(self):
        obj,_=make_observer(vehicle_profile='30618',enabled=True,artifact=synthetic_artifact())
        obj.reset(velocity=1.5)
        for i in range(20):
            t=i*.05;e=obj.step(t,Sample(t,0.),Sample(t,0.),Sample(t,0.))
            self.assertNotEqual(e.mode,'STOPPED')
            self.assertNotEqual(e.front_status,'ACCEPTED')

    def test_common_jump_quarantine_preserved(self):
        obj,_=make_observer(vehicle_profile='30618',enabled=True,artifact=synthetic_artifact())
        for i in range(50):
            t=i*.05;z=5. if i<20 else 10.
            e=obj.step(t,Sample(t,0.),Sample(t,z),Sample(t,z))
            if 21<=i<=40:self.assertNotEqual(e.mode,'REACQUIRING')
        self.assertGreater(obj.reacquire_blocked_until,1.)

    def test_invalid_numbers_and_boolean_flag(self):
        for v in (float('nan'),float('inf'),0.,6.,True,'1'):
            with self.assertRaises(ValueError):ForceParameters(v,7.,1.)
        with self.assertRaises(TypeError):make_observer(enabled='false')


class ObjectiveTests(unittest.TestCase):
    def test_joint_center_and_label_bounds(self):
        center,labels=joint_vectors([1.,6.,.9,1.4,8.,1.3])
        self.assertEqual(center,ForceParameters(1.2,7.,1.1))
        self.assertEqual(set(labels),{'30618','30639'})
        with self.assertRaises(ValueError):joint_vectors([1.,2.,3.])

    def test_shrinkage_exact_partial_minimizer(self):
        theta=[1.,6.,.9,1.4,8.,1.3];scales=[1.,7.,1.]
        residuals=shrinkage_residuals(theta,scales)
        direct=SHRINKAGE*.5*sum(((x-y)/s)**2 for x,y,s in zip(theta[:3],theta[3:],scales))
        self.assertAlmostEqual(sum(r*r for r in residuals),direct)
        self.assertEqual(shrinkage_residuals([1.,7.,1.]*2,scales),[0.]*6)

    def test_soft_l1_data_only_transform(self):
        for x in (-20.,-.1,0.,.1,20.):
            y=soft_l1_residual(x)
            self.assertAlmostEqual(y*y,2*(math.hypot(1,x/.2)-1))
        self.assertAlmostEqual(soft_l1_residual(1e-10),5e-10)
        with self.assertRaises(ValueError):soft_l1_residual(float('nan'))

    def test_shared_budget_cannot_be_overrun(self):
        budget=ObjectiveBudget()
        for _ in range(MAX_RESIDUAL_CALLS):budget.invoke(lambda:0.)
        with self.assertRaises(RuntimeError):budget.invoke(lambda:0.)
        self.assertEqual(budget.calls,MAX_RESIDUAL_CALLS)

    def test_failure_consumes_budget(self):
        budget=ObjectiveBudget()
        with self.assertRaises(ZeroDivisionError):budget.invoke(lambda:1/0)
        self.assertEqual(budget.calls,1)

    def test_missing_dependencies_not_authorized(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=probe(Path(tmp)/'H42.zip',Path(tmp)/'H43.zip')
        self.assertFalse(result['training_authorized'])
        self.assertFalse(result['native_verifiers_run'])
        self.assertEqual(result['stage'],'DEPENDENCY_PENDING')

    def test_even_transport_success_is_not_a_native_lock(self):
        with patch('dependency_probe.inspect_component',return_value={'payload_schema_verified':False}):
            result=probe(Path('teacher'),Path('atlas'))
        self.assertFalse(result['training_authorized'])
        self.assertFalse(result['native_verifiers_run'])

if __name__=='__main__':unittest.main()
