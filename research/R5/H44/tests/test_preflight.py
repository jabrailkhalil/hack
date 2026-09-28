"""Interface and fail-closed tests, not teacher verification or accuracy tests."""
from dataclasses import asdict, fields
import inspect
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import interface as i
import baseline_preflight as b
from reserve_odometry.core import Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.cfg, self.readout, self.ops = i.profile()

    def test_complete_profile(self):
        self.assertEqual(set(asdict(self.cfg)), {f.name for f in fields(i.Config)})
        self.assertEqual(self.ops, b.g.OPS)
        self.assertEqual(asdict(self.readout), {'gain': 1., 'holdoff_s': .5})
        self.assertEqual(self.cfg.common_mode_quarantine_s, 1.5)
        self.assertEqual(self.cfg.adaptation_tau_s, .5)
        self.assertEqual(self.cfg.wheel_time_compensation, 0.)

    def test_effective_identity_exact(self):
        result = i.with_effective(self.cfg, i.effective(self.cfg))
        self.assertEqual(asdict(result), asdict(self.cfg))
        self.assertIsNot(result, self.cfg)

    def test_only_three_fields_can_change(self):
        theta = tuple(x * 1.01 for x in i.effective(self.cfg))
        before = asdict(self.cfg)
        result = i.with_effective(self.cfg, theta)
        changed = {k for k in before if before[k] != asdict(result)[k]}
        self.assertEqual(changed, set(i.PARAMETERS))
        self.assertEqual(before, asdict(self.cfg))
        for a, t in zip(i.effective(result), theta):
            self.assertAlmostEqual(a, t, delta=2e-14)

    def test_effective_force_matches_runtime_at_low_speed(self):
        observer = GuardedReadoutObserver(self.cfg, readout=self.readout)
        force, power, brake = i.effective(self.cfg)
        self.assertAlmostEqual(observer.drive_target(1., 1.), force, places=14)
        self.assertAlmostEqual(observer.drive_target(1., 35.), power / 35., places=14)
        self.assertAlmostEqual(observer.drive_target(-1., 5.), -math.tanh(5./.2)*brake, places=14)

    def test_invalid_theta(self):
        for theta in ((1., 2.), (1.,2.,3.,4.), (0.,2.,3.), (-1.,2.,3.),
                      (float('nan'),2.,3.), (1.,float('inf'),3.)):
            with self.subTest(theta=theta), self.assertRaises(ValueError):
                i.with_effective(self.cfg, theta)

    def test_baseline_factory_exact_full_state_2000_ticks(self):
        a = GuardedReadoutObserver(self.cfg, readout=self.readout)
        c = i.with_effective(self.cfg, i.effective(self.cfg))
        z = GuardedReadoutObserver(c, readout=self.readout)
        for k in range(2000):
            t = k * .05
            ts = (k // 2) * .1
            velocity = 5. + .1 * math.sin(ts)
            cmd = Sample(t, -.15 if k % 300 < 60 else .1)
            front = None if 500 <= k < 600 else Sample(ts, velocity)
            rear = None if 500 <= k < 600 else Sample(ts, velocity)
            self.assertEqual(a.step(t, cmd, front, rear), z.step(t, cmd, front, rear))
            self.assertEqual(vars(a), vars(z))

    def test_training_entry_is_blocked_even_with_expected_receipt(self):
        with patch.object(b.sqlite3, 'connect', side_effect=AssertionError('unexpected IO')):
            with self.assertRaises(i.DependencyPending):
                i.training_entrypoint({'expected_hash': 'not a verified payload', 'passed': True})

    def test_no_new_runtime_signature(self):
        self.assertEqual(tuple(inspect.signature(GuardedReadoutObserver.step).parameters),
                         ('self', 't', 'command', 'front', 'rear'))


class RoleAndEvidenceTests(unittest.TestCase):
    def test_other_roles_denied_before_io(self):
        store = b.DevelopmentStore(Path('/intentionally/nonexistent'))
        with patch.object(b.sqlite3, 'connect', side_effect=AssertionError('unexpected IO')):
            for role in ('train', 'validation', 'test'):
                with self.subTest(role=role), self.assertRaises(PermissionError):
                    store.load(store.plan['splits'][role][0], role)

    def test_spoofed_role_denied_before_io(self):
        store = b.DevelopmentStore(Path('/intentionally/nonexistent'))
        with patch.object(b.sqlite3, 'connect', side_effect=AssertionError('unexpected IO')):
            for role in ('train', 'validation', 'test'):
                with self.subTest(role=role), self.assertRaises(PermissionError):
                    store.load(store.plan['splits'][role][0], 'development')

    def test_unknown_bag_denied(self):
        store = b.DevelopmentStore(Path('/intentionally/nonexistent'))
        with self.assertRaises(PermissionError):
            store.load('../not-a-bag', 'development')

    def test_existing_evidence_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'result.json'
            b.write(path, {'first': True})
            old = path.read_bytes()
            with self.assertRaises(FileExistsError):
                b.write(path, {'replacement': True})
            self.assertEqual(path.read_bytes(), old)

    def test_missing_reference_remains_missing(self):
        cfg, readout, _ = i.profile()
        events = b.np.array([(k*.1, ch, .0 if ch == 0 else 5.)
                            for k in range(101) for ch in range(3)], float)
        factory = b.partial(GuardedReadoutObserver, readout=readout)
        out = b.g.compare(events, {'master': [], 'rover': []}, {'main': (factory, cfg)})
        for receiver in out['receivers'].values():
            self.assertIsNone(receiver['main']['rmse'])
            self.assertEqual(receiver['main']['n'], 0)


if __name__ == '__main__':
    unittest.main()
