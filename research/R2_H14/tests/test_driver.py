from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/research_R2_H14'))
from common import ev
from run import RoleStore,score,r2_decision,NAMES
import numpy as np

class DriverTests(unittest.TestCase):
    def test_roles_deny_before_sqlite_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=RoleStore(Path(tmp)/'access.json')
            for role in ('test','development','train'):
                test_bag=s.plan['splits']['test'][0]
                with patch('sqlite3.connect',side_effect=AssertionError('Must not open data')):
                    with self.assertRaises(PermissionError):s.load(test_bag,role)
    def test_paired_score_and_off_unchanged(self):
        events=np.asarray([(k*.05,ch, .1 if ch==0 else 4.+.1*k*.05)
                           for k in range(400) for ch in ([0,1] if k%2==0 else [0,2])],float)
        refs={'master':[(k*.05,4.+.1*k*.05) for k in range(400)],'rover':[]}
        row,diag=score(events,refs)
        self.assertEqual(row['receivers']['master']['v7_baseline']['n'],row['receivers']['master']['H14_off']['n'])
        self.assertGreater(diag['H14_async_pairs']['async_updates'],0)
        self.assertIsNone(row['receivers']['rover']['H14_async_pairs']['rmse'])

if __name__=='__main__':unittest.main()
