"""Regression for advancing prefix freshness with actual message arrivals."""
import sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src/reserve_odometry'))
from test_map import fixture
from geo_math import LocalENU
from start_prefix import initial_anchor

class Arrival(unittest.TestCase):
    def test_stale_velocities_at_later_arrival(self):
        m=fixture();llh=list(LocalENU(m['frame']['origin']['llh']).reverse((1,0,0)))
        events=[dict(receiver=r,kind='vel',record_ns=i,stamp_ns=0,linear=[1.,0.,0.]) for i,r in enumerate(('master','rover'))]
        events.append(dict(receiver='master',kind='fix',record_ns=2_000_000_000,stamp_ns=0,status=0,position=llh))
        self.assertEqual(initial_anchor(events,0,m)['status'],'UNLOCALIZED')

if __name__=='__main__':unittest.main()
