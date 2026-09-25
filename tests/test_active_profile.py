"""Active champion, inner-v5 baseline and historical evidence isolation."""
import json
from pathlib import Path
import unittest
from dataclasses import asdict
from reserve_odometry.core import Config

ROOT=Path(__file__).resolve().parents[1]


class ActiveProfileTests(unittest.TestCase):
    def _yaml_model(self,path):
        actual={}
        for line in path.read_text().splitlines():
            key,sep,value=line.strip().partition(':')
            if sep and key.startswith('model.'):
                actual[key[6:]]=float(value)
        return actual

    def test_canonical_launch_is_guarded_v7(self):
        launch=(ROOT/'src/reserve_odometry/launch/odometry.launch.py').read_text()
        self.assertIn("guarded_odometry_node",launch)
        self.assertIn("champion_v8.yaml",launch)
        setup=(ROOT/'src/reserve_odometry/setup.py').read_text()
        self.assertIn("guarded_odometry_node = reserve_odometry.guarded_node:main",setup)

    def test_guarded_profile_preserves_v5_inner_physics(self):
        v5=json.loads((ROOT/'src/reserve_odometry/config/adaptive_v5.json').read_text())['config']
        guarded=json.loads((ROOT/'src/reserve_odometry/config/champion_v8.json').read_text())
        self.assertEqual(guarded['config'],dict(v5,wheel_time_compensation=0.0,common_mode_quarantine_s=1.5))
        self.assertEqual(guarded['readout'],{'gain':1.0,'holdoff_s':0.5})
        self.assertEqual(self._yaml_model(ROOT/'src/reserve_odometry/config/default.yaml'),v5)
        self.assertEqual(asdict(Config(**v5)),dict(v5,wheel_time_compensation=0.0,common_mode_quarantine_s=0.0))

    def test_champion_metrics_are_explicitly_qualified(self):
        p=json.loads((ROOT/'reports/champion_v7/PROMOTION.json').read_text())
        self.assertEqual(p['active_profile'],'guarded_readout_v7_plus_zero_lock_guard')
        self.assertLess(p['clean_validation']['group_macro_rmse_mps'],
                        p['clean_validation']['baseline_v5_mps'])
        self.assertLessEqual(p['fault_validation']['group_macro_event_rmse_mps'],
                             p['fault_validation']['baseline_v5_mps']*1.005)
        self.assertIn('Not an independent final test',p['qualification'])

    def test_inner_v5_default_remains_reproducible(self):
        launch=(ROOT/'src/reserve_odometry/launch/v5_odometry.launch.py').read_text()
        self.assertIn("executable='odometry_node'",launch)
        self.assertIn("config' / 'default.yaml",launch)
        self.assertEqual(self._yaml_model(ROOT/'src/reserve_odometry/config/default.yaml')['adaptation_tau_s'],.5)

    def test_historical_v4_archive_is_not_rewritten(self):
        frozen=(ROOT/'src/reserve_odometry/config/frozen_v4.yaml').read_bytes()
        self.assertNotEqual(frozen,(ROOT/'src/reserve_odometry/config/default.yaml').read_bytes())

    def test_experimental_in_filter_compensation_is_not_active_inner_state(self):
        self.assertEqual(Config().wheel_time_compensation,0.0)
        self.assertNotIn('wheel_projection_gain',asdict(Config()))
        self.assertNotIn('disturbance_decay_s',asdict(Config()))


if __name__=='__main__':
    unittest.main()
