from pathlib import Path
import copy
import inspect
import json
import math
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
MODULE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(MODULE), str(ROOT / 'src/reserve_odometry')]
from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from features import CausalFeatureProbe, FEATURE_NAMES, in_domain
from offline_labels import TeacherPoint, unique_nearest, proxy_pair_labels
from dependency_status import check


def profile():
    raw = json.loads((ROOT / 'src/reserve_odometry/config/champion_v8.json').read_text())
    return Config(**raw['config']), ReadoutConfig(**raw['readout'])


def pair():
    a, r = profile()
    b, s = profile()
    probe = CausalFeatureProbe(a, readout=r)
    native = GuardedReadoutObserver(b, readout=s)
    probe.reset(velocity=2.0)
    native.reset(velocity=2.0)
    return probe, native


def warm(probe, n=24, sign=1):
    for k in range(n):
        t = k * .05
        probe.step(t, Sample(t, 0.), Sample(t, 2. * sign), Sample(t, 2. * sign))
    return (n-1) * .05


class FeatureTests(unittest.TestCase):
    def test_profile_is_canonical_v8(self):
        c, r = profile()
        self.assertEqual((c.common_mode_quarantine_s, c.adaptation_tau_s,
                          c.wheel_time_compensation, r.gain, r.holdoff_s), (1.5, .5, 0, 1, .5))

    def test_native_state_and_estimate_equality(self):
        p, b = pair()
        for k in range(2500):
            t = k * .05
            v = 2 + .15 * math.sin(k / 40.)
            f, r = Sample(t, v), Sample(t, v + .02)
            command = Sample(t, .3 * math.sin(k / 50.))
            segment = k % 500
            if 100 <= segment < 110:
                f = Sample(t, v + 5)
            elif 120 <= segment < 135:
                f, r = Sample(t, v + 5), Sample(t, v + 5)
            elif 150 <= segment < 175:
                f = r = None
            elif 250 <= segment < 260:
                f = r = Sample(t, 0.)
            elif 350 <= segment < 353:
                command = None
            self.assertEqual(p.step(t, command, f, r), b.step(t, command, f, r))
            for field, value in vars(b).items():
                self.assertEqual(getattr(p, field), value, field)

    def test_exactly_eight_features_ready(self):
        p, _ = pair(); warm(p)
        self.assertEqual(len(FEATURE_NAMES), 8)
        for row in p.last_features:
            self.assertEqual(row.reason, 'READY')
            self.assertTrue(in_domain(row.values))

    def test_only_vehicle_inputs(self):
        self.assertEqual(list(inspect.signature(CausalFeatureProbe.step).parameters),
                         ['self', 't', 'command', 'front', 'rear'])
        p, _ = pair()
        for key in ('gnss', 'teacher', 'accepted', 'available_after_bag_record_ns', 'bag_id'):
            with self.assertRaises(TypeError):
                p.step(0., **{key: 1})

    def test_no_current_sample_in_history_mean(self):
        p, _ = pair(); t = warm(p)
        expected = [sum(v for _, v in h)/len(h) for h in p._h47_histories]
        t += .05
        p.step(t, Sample(t, 0.), Sample(t, 2.12), Sample(t, 2.12))
        for i, row in enumerate(p.last_features):
            self.assertEqual(row.reason, 'READY')
            self.assertEqual(row.values[7], expected[i])

    def test_history_bounded_by_time_and_count(self):
        p, _ = pair(); warm(p, 500)
        for h in p._h47_histories:
            self.assertLessEqual(len(h), 16)
            self.assertLessEqual(p.t - h[0][0], 1.)
        for j in range(30):
            t = p.t + .05
            p.step(t, Sample(t, 0.))
        self.assertTrue(all(len(h) == 0 for h in p._h47_histories))

    def test_duplicate_does_not_add(self):
        p, _ = pair(); t = warm(p)
        before = copy.deepcopy(p._h47_histories)
        p.step(t+.05, Sample(t+.05, 0.), Sample(t, 2.), Sample(t, 2.))
        self.assertEqual(p._h47_histories, before)
        self.assertTrue(all(r.values is None for r in p.last_features))

    def test_old_sample_does_not_replace_previous(self):
        p, _ = pair(); t = warm(p)
        old = list(p._h47_previous)
        p.step(t+.05, Sample(t+.05, 0.), Sample(t-.1, 2.), Sample(t-.1, 2.))
        self.assertEqual(p._h47_previous, old)

    def test_future_sample_does_not_append(self):
        p, _ = pair(); t = warm(p)
        before = copy.deepcopy(p._h47_histories)
        p.step(t+.05, Sample(t+.05, 0.), Sample(t+.10, 2.), Sample(t+.10, 2.))
        self.assertEqual(p._h47_histories, before)
        self.assertTrue(all(r.values is None for r in p.last_features))

    def test_native_tolerance_does_not_authorize_future_feature(self):
        p, _ = pair(); t = warm(p) + .05
        p.step(t, Sample(t, 0.), Sample(t+5e-10, 2.), Sample(t+5e-10, 2.))
        self.assertTrue(all(r.values is None for r in p.last_features))

    def test_stale_command_abstains(self):
        p, _ = pair(); t = warm(p) + .05
        p.step(t, Sample(t-1., .5), Sample(t, 2.), Sample(t, 2.))
        self.assertTrue(p.last_estimate.command_stale)
        self.assertTrue(all(r.values is None for r in p.last_features))

    def test_future_command_abstains(self):
        p, _ = pair(); t = warm(p) + .05
        p.step(t, Sample(t+.01, .5), Sample(t, 2.), Sample(t, 2.))
        self.assertTrue(all(r.values is None for r in p.last_features))

    def test_nonfinite_wheel_does_not_append(self):
        for val in (math.nan, math.inf, -math.inf):
            p, _ = pair(); t = warm(p) + .05
            before = copy.deepcopy(p._h47_histories)
            p.step(t, Sample(t, 0.), Sample(t, val), Sample(t, val))
            self.assertEqual(p._h47_histories, before)

    def test_domain_abstention_not_clipping(self):
        p, _ = pair(); t = warm(p) + .05
        p.step(t, Sample(t, 0.), Sample(t, 2.44), Sample(t, 2.44))
        self.assertEqual(p.last_estimate.mode, 'FUSED')
        self.assertTrue(all(r.reason == 'OUT_OF_DOMAIN' and r.values is None
                            for r in p.last_features))

    def test_missing_rate_history(self):
        p, _ = pair(); warm(p, 2)
        self.assertTrue(all(r.reason == 'RATE_HISTORY_MISSING' for r in p.last_features))

    def test_channel_permutation_equivariance(self):
        p, _ = pair(); q, _ = pair()
        for k in range(100):
            t = .05*k
            f, r = Sample(t, 2.+.01*math.sin(k)), Sample(t, 2.02)
            p.step(t, Sample(t, 0.), f, r)
            q.step(t, Sample(t, 0.), r, f)
            self.assertEqual(p.last_features, tuple(reversed(q.last_features)))

    def test_prefix_unchanged_by_later_suffix(self):
        p, _ = pair(); q, _ = pair()
        prefix = []
        for k in range(40):
            t = k*.05; args = (t, Sample(t, 0.), Sample(t, 2.), Sample(t, 2.))
            prefix.append((p.step(*args), p.last_features))
            self.assertEqual((q.step(*args), q.last_features), prefix[-1])
        frozen = copy.deepcopy(prefix)
        for k in range(40, 80):
            t = k*.05
            p.step(t, Sample(t, .5), Sample(t, 9.), None)
        self.assertEqual(prefix, frozen)

    def test_disabled_collection_exact_native(self):
        c, r = profile(); p = CausalFeatureProbe(c, readout=r, collect=False)
        c2, r2 = profile(); b = GuardedReadoutObserver(c2, readout=r2)
        for k in range(60):
            t = k*.05; args=(t, Sample(t, .2), Sample(t, 2.), Sample(t, 2.))
            self.assertEqual(p.step(*args), b.step(*args))
        self.assertEqual(p.last_features, (None, None))
        self.assertTrue(all(not h for h in p._h47_histories))

    def test_reset_clears_only_auxiliary_with_native_reset(self):
        p, b = pair(); warm(p)
        p.reset(velocity=1.5, position=7.); b.reset(velocity=1.5, position=7.)
        self.assertEqual(p.last_features, (None, None))
        for field, value in vars(b).items():
            self.assertEqual(getattr(p, field), value)
        self.assertTrue(all(not h for h in p._h47_histories))

    def test_time_errors_do_not_mutate(self):
        p, _ = pair(); t = warm(p)
        for bad in (t, t-1., t+1., math.nan):
            before = copy.deepcopy(vars(p))
            with self.assertRaises(ValueError): p.step(bad)
            self.assertEqual(vars(p), before)

    def test_low_speed_never_ready(self):
        c, r=profile(); p=CausalFeatureProbe(c, readout=r); p.reset(velocity=.3)
        for k in range(50):
            t=k*.05; p.step(t, Sample(t,0), Sample(t,.3), Sample(t,.3))
            self.assertTrue(all(row.values is None for row in p.last_features))

    def test_symmetric_negative_motion(self):
        p, _ = pair(); c, r=profile(); c.travel_direction=-1.
        n=CausalFeatureProbe(c,readout=r); n.reset(velocity=-2.)
        for k in range(40):
            t=k*.05
            p.step(t,Sample(t,0),Sample(t,2.),Sample(t,2.))
            n.step(t,Sample(t,0),Sample(t,-2.),Sample(t,-2.))
        self.assertEqual(tuple(x.values for x in p.last_features),tuple(x.values for x in n.last_features))

    def test_true_stop_clears_auxiliary(self):
        c,r=profile(); p=CausalFeatureProbe(c,readout=r); p.reset(velocity=0.)
        for k in range(30):
            t=k*.05; p.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
        self.assertEqual(p.last_estimate.mode,'STOPPED')
        self.assertTrue(all(not h for h in p._h47_histories))

    def test_invalid_collect_type(self):
        c,r=profile()
        with self.assertRaises(ValueError): CausalFeatureProbe(c,readout=r,collect=1)

    def test_not_a_reliability_model(self):
        p,_=pair(); warm(p)
        self.assertFalse(hasattr(p,'predict_proba'))
        self.assertFalse(hasattr(p,'coefficients'))


class OfflineLabelTests(unittest.TestCase):
    def labels(self,f,r,accepted=True,ready=True):
        return proxy_pair_labels(Sample(0.,f),Sample(0.,r),TeacherPoint(0.,2.,accepted),
                                 TeacherPoint(0.,2.,accepted),features_ready=ready)
    def test_clean_pair(self): self.assertEqual(self.labels(2.,2.1),(0,0))
    def test_front_positive_and_negative_error(self):
        self.assertEqual(self.labels(2.6,2.),(1,0))
        self.assertEqual(self.labels(1.4,2.),(1,0))
    def test_rear_positive_and_negative_error(self):
        self.assertEqual(self.labels(2.,2.6),(0,1))
        self.assertEqual(self.labels(2.,1.4),(0,1))
    def test_common_fault_abstention(self):
        self.assertIsNone(self.labels(2.6,2.6))
        self.assertIsNone(self.labels(1.4,1.4))
    def test_intermediate_error_abstention(self): self.assertIsNone(self.labels(2.3,2.))
    def test_low_speed_abstention(self): self.assertIsNone(self.labels(0.,2.))
    def test_teacher_disallowed(self): self.assertIsNone(self.labels(2.6,2.,accepted=False))
    def test_features_disallowed(self): self.assertIsNone(self.labels(2.6,2.,ready=False))
    def test_teacher_does_not_supply_direction(self): self.assertEqual(self.labels(-2.6,-2.),(1,0))
    def test_unique_nearest_and_no_extrapolation(self):
        t=TeacherPoint(1.,2.,True)
        self.assertEqual(unique_nearest([t],1.02),t)
        self.assertIsNone(unique_nearest([t],1.2))
    def test_ties_duplicate_and_ambiguous_abstain(self):
        t=TeacherPoint(1.,2.,True)
        self.assertIsNone(unique_nearest([t,t],1.))
        self.assertIsNone(unique_nearest([TeacherPoint(.99,2.,True),TeacherPoint(1.01,2.,True)],1.))
        self.assertIsNone(unique_nearest([TeacherPoint(1.,2.,False)],1.))
    def test_wrong_teacher_time(self):
        self.assertIsNone(proxy_pair_labels(Sample(0,2.),Sample(0,2.),TeacherPoint(.1,2.,True),
                          TeacherPoint(0,2.,True),features_ready=True))
    def test_nonfinite_rejected(self):
        self.assertIsNone(self.labels(math.nan,2.))
        self.assertIsNone(unique_nearest([TeacherPoint(0,math.inf,True)],0.))


class DependencyTests(unittest.TestCase):
    def test_missing_never_authorizes(self):
        with tempfile.TemporaryDirectory() as d:
            r=check(Path(d)/'teacher.zip',Path(d)/'atlas.zip')
            self.assertEqual(r['stage'],'DEPENDENCY_PENDING')
            self.assertFalse(r['is_dependency_lock'])
            self.assertFalse(r['training_authorized'])
            self.assertFalse(r['combined_lock_created'])
    def test_receipt_is_not_archive(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'receipt.json'; p.write_text('{"component_ready":true}')
            r=check(p,p)
            self.assertEqual(r['stage'],'DEPENDENCY_MISMATCH')
            self.assertFalse(r['training_authorized'])
    def test_output_cannot_be_a_lock(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'DEPENDENCIES.lock.json'
            result=subprocess.run([sys.executable,str(MODULE/'dependency_status.py'),
                  '--teacher-zip',str(Path(d)/'t'), '--atlas-zip',str(Path(d)/'a'),
                  '--output',str(p)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(p.exists())
    def test_no_overwrite_existing_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'receipt.json'; p.write_text('original')
            result=subprocess.run([sys.executable,str(MODULE/'dependency_status.py'),
                  '--teacher-zip',str(Path(d)/'t'), '--atlas-zip',str(Path(d)/'a'),
                  '--output',str(p)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(p.read_text(),'original')


if __name__=='__main__': unittest.main()
