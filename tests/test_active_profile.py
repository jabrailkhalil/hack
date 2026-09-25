"""Current champion and rejected-experiment isolation; no historical score reuse."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from dataclasses import asdict
from reserve_odometry.core import Config
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from evidence_archive import read_v4


class ActiveProfileTests(unittest.TestCase):
    def test_current_default_is_the_selected_profile(self):
        promotion=json.loads((ROOT/'reports/research_v6/PROMOTION.json').read_text())
        actual={}
        for line in (ROOT/'src/reserve_odometry/config/default.yaml').read_text().splitlines():
            key,sep,value=line.strip().partition(':')
            if sep and key.startswith('model.'):
                actual[key[6:]]=float(value)
        self.assertEqual(actual,promotion['config'])
        self.assertEqual(actual,asdict(Config(**actual)))
        expected=json.loads((ROOT/promotion['profile_json']).read_text())['config']
        self.assertEqual(actual,expected)
        self.assertEqual(actual['adaptation_tau_s'],.5)
        self.assertFalse(promotion['independent_test_evaluated'])

    def test_active_source_hashes_are_pinned_separately(self):
        promotion=json.loads((ROOT/'reports/research_v6/PROMOTION.json').read_text())
        for path,digest in promotion['source_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)

    def test_rejected_experimental_runtime_is_not_deployed(self):
        for name in ('core.py','node.py','timeline.py','route.py'):
            path='src/reserve_odometry/reserve_odometry/'+name
            self.assertEqual((ROOT/path).read_bytes(),read_v4(path))
        self.assertNotIn('wheel_projection_gain',asdict(Config()))
        self.assertNotIn('disturbance_decay_s',asdict(Config()))

    def test_original_v4_default_is_retained_exactly(self):
        self.assertEqual((ROOT/'src/reserve_odometry/config/frozen_v4.yaml').read_bytes(),
                         read_v4('src/reserve_odometry/config/default.yaml'))

    def test_five_hypotheses_rejected_not_silently_promoted(self):
        rejected=[]
        for round_number in (1,2):
            d=json.loads((ROOT/f'reports/research_v6/round{round_number}/decision.json').read_text())
            self.assertEqual(d['selected'],'v5_adaptive_05s')
            self.assertFalse(d['test_evaluated'])
            for name,c in d['candidates'].items():
                if name not in ('v4_default','v5_adaptive_05s'):
                    self.assertFalse(c['eligible'])
                    self.assertIn('aggregate_regression',c['rejection_reasons'])
                    rejected.append(name)
        self.assertEqual(len(set(rejected)),5)
