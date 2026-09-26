import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import *
from foundation import Probe
class FoundationTests(unittest.TestCase):
    def test_profile_and_pins(self):
        self.assertEqual(pins()['verified_baseline_files'],301)
    def test_roles_before_io(self):
        s=Store()
        for r in ('test','validation'):
            with self.assertRaises(PermissionError):s.load(s.plan['splits'][r][0],r)
        with self.assertRaises(PermissionError):s.load(s.plan['splits']['development'][0],'train')
    def test_nonintervention(self):
        c,_=profile();o=Probe(c)
        for i in range(1000):
            t=i*.05;f=Sample(t,10.) if i%2==0 else None
            o.step(t,Sample(t,.4),f,f)
        self.assertGreater(o.stats['qualifying_ticks'],200)
    def test_piecewise_oracle(self):
        c,_=profile()
        for q in (0,.01,.1,.5,.9,1):
            u=c.command_deadband+(1-c.command_deadband)*q**(1/c.command_exponent)
            for v in (0.,1.,3.,6.,10.,25.,40.):
                qq,f,cap,a,b=targets(c,u,v)
                d=0 if f<=cap else (qq*(f-cap)/c.mass_kg if qq*f<=cap else (1-qq)*cap/c.mass_kg)
                self.assertAlmostEqual(b-a,d,14);self.assertGreaterEqual(b-a,-1e-14)
                self.assertLessEqual(b-a,f/(4*c.mass_kg)+1e-14)
if __name__=='__main__':unittest.main()
