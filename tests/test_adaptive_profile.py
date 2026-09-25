"""Run the established observer safety scenarios with the selected v5 profile."""
from dataclasses import asdict
import json
from pathlib import Path
from unittest.mock import patch
import test_core
from reserve_odometry.core import Config, Observer

ROOT = Path(__file__).resolve().parents[1]


class AdaptiveProfileTests(test_core.ObserverTests):
    def setUp(self):
        self.config = json.loads((ROOT / 'src/reserve_odometry/config/adaptive_v5.json').read_text())['config']
        # Tests with explicit configs still exercise their specific boundary.
        def selected(config=None):
            return Observer(config if config is not None else Config(**self.config))
        self.patch = patch.object(test_core, 'Observer', selected)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_only_adaptation_changes_from_main(self):
        main = json.loads((ROOT / 'src/reserve_odometry/config/candidates_v3/balanced_physics.json').read_text())['config']
        self.assertEqual(self.config, dict(main, adaptation_tau_s=.5))
        actual = {}
        for line in (ROOT / 'src/reserve_odometry/config/adaptive_v5.yaml').read_text().splitlines():
            key, sep, value = line.strip().partition(':')
            if sep and key.startswith('model.'):
                actual[key[6:]] = float(value)
        self.assertEqual(dict(actual, wheel_time_compensation=0.0, common_mode_quarantine_s=0.0),
                         asdict(Config(**self.config)))
