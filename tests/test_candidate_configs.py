"""Validate all exported candidates without offline research dependencies."""
from dataclasses import asdict
import json
from pathlib import Path
import unittest
from reserve_odometry.core import Config, Observer, Sample

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / 'src/reserve_odometry/config/candidates_v3'


class CandidateConfigs(unittest.TestCase):
    def test_exported_configs_are_valid(self):
        files = list(CANDIDATES.glob('*.json'))
        self.assertEqual(len(files), 4)
        for path in files:
            data = json.loads(path.read_text())
            config = Config(**data['config'])
            if path.stem == 'baseline_v2':
                self.assertEqual(asdict(config), asdict(Config()))
            if data['fitted']:
                self.assertTrue(data['solver_success'])

    def test_calibrated_configs_constant_speed(self):
        for path in CANDIDATES.glob('*.json'):
            observer = Observer(Config(**json.loads(path.read_text())['config']))
            for i in range(101):
                t = i * .05
                e = observer.step(t, Sample(t, 0), Sample(t, 5), Sample(t, 5))
            self.assertLess(abs(e.v - 5), .1)
            self.assertGreater(e.s, 24.)

    def test_default_matches_eligible_selection(self):
        decision = json.loads((ROOT / 'reports/research_v3/decision.json').read_text())
        name = decision['selected']
        self.assertTrue(decision['candidates'][name]['eligible'])
        expected = json.loads((CANDIDATES / (name + '.json')).read_text())['config']
        # Files emitted here contain scalar float model parameters, no YAML features.
        actual = {}
        for line in (ROOT / 'src/reserve_odometry/config/default.yaml').read_text().splitlines():
            line = line.strip()
            if line.startswith('model.'):
                key, value = line.split(':', 1)
                actual[key[6:]] = float(value)
        self.assertEqual(actual, expected)
        self.assertFalse(decision['test_evaluated'])


if __name__ == '__main__':
    unittest.main()
