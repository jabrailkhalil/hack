"""Explicit fitted-profile tests; FIT_ROOT must name the immutable fitted JSONs."""
import unittest,os,sys,json,math
from pathlib import Path
from dataclasses import asdict
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from interface import profile,with_effective,effective,PARAMETERS
from reserve_odometry.core import Config,Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver

@unittest.skipUnless(os.environ.get('FIT_ROOT'),'Requires explicit measured fitted profiles')
class FittedTests(unittest.TestCase):
    def profiles(self):
        base,r,_=profile()
        for n in ('gnss','wheel'):
            d=json.loads((Path(os.environ['FIT_ROOT'])/(n+'.json')).read_text())
            yield n,Config(**d['config']),r,base
    def test_three_fields_and_inverse(self):
        for n,c,r,b in self.profiles():
            self.assertEqual({k for k,v in asdict(c).items() if v!=getattr(b,k)},set(PARAMETERS))
            np.testing.assert_allclose(effective(c),json.loads((Path(os.environ['FIT_ROOT'])/(n+'.json')).read_text())['effective'],rtol=0,atol=0)
            off=with_effective(b,effective(b));self.assertEqual(off,b)
    def test_fixed_profiles_finite_and_bounded(self):
        for n,c,r,b in self.profiles():
            o=GuardedReadoutObserver(c,readout=r);keys=None
            for k in range(12000):
                t=k*.05;u=.6 if k%400<200 else -.25
                s=None if 160<k%400<200 else Sample(t,3.+.4*math.sin(t))
                e=o.step(t,Sample(t,u),s,s)
                self.assertTrue(all(math.isfinite(v) for v in (e.v,e.s,e.variance_v,e.variance_s,e.disturbance)))
                self.assertLessEqual(abs(o.v),c.max_speed_mps);self.assertLessEqual(abs(o.disturbance),c.disturbance_limit_mps2)
                if keys is None:keys=set(vars(o))
                self.assertEqual(set(vars(o)),keys)
    def test_yaml_values_exact(self):
        for n,c,r,b in self.profiles():
            text=(Path(__file__).resolve().parents[1]/'variants'/f'{n}.yaml').read_text()
            flat={k.strip():v.strip() for line in text.splitlines() if ':' in line and not line.lstrip().startswith('#') for k,v in [line.split(':',1)]}
            for key,v in asdict(c).items():self.assertEqual(float(flat['model.'+key]),v)
            self.assertEqual(float(flat['readout.gain']),r.gain);self.assertEqual(float(flat['readout.holdoff_s']),r.holdoff_s)
            self.assertEqual(float(flat['rate_hz']),20.);self.assertEqual(float(flat['alignment_delay_s']),0.)
    def test_prefix_stale_future_reset(self):
        for n,c,r,b in self.profiles():
            a=GuardedReadoutObserver(c,readout=r);z=GuardedReadoutObserver(c,readout=r)
            for k in range(200):
                t=k*.05;s=Sample(t,4.);cmd=Sample(t,.1)
                self.assertEqual(a.step(t,cmd,s,s),z.step(t,cmd,s,s))
            # A future wheel must be rejected, not used as a high-gain target.
            e=a.step(10.,Sample(10.,.1),Sample(11.,30.),Sample(11.,30.))
            self.assertNotEqual(e.front_status,'ACCEPTED');self.assertNotEqual(e.rear_status,'ACCEPTED')
            a.reset();fresh=GuardedReadoutObserver(c,readout=r)
            self.assertEqual(a.step(0.,Sample(0.,0),Sample(0.,0),Sample(0.,0)),fresh.step(0.,Sample(0.,0),Sample(0.,0),Sample(0.,0)))
if __name__=='__main__':unittest.main()
