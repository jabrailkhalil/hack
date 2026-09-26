"""Mechanism and runtime invariants; no accuracy claims from synthetic cases."""
import unittest
from dataclasses import asdict
from model import *
from develop import scored, low_speed_windows, DevelopmentStore, STATUS
from reserve_odometry.core import Sample

FITTED = [1.4431384776192366,8.539592014957336,.7797233699048588]
CONTROL = [1.1117412748779552,7.084173603327819,.7887928857012503]

class EnabledTests(unittest.TestCase):
    def test_exact_configs_and_runtime_class(self):
        for theta in (FITTED,CONTROL):
            o=factory(theta)
            self.assertIs(type(o),GuardedReadoutObserver)
            self.assertEqual(set(vars(o)),set(vars(factory())))
            self.assertEqual(o.c.common_mode_quarantine_s,1.5)
            self.assertEqual(o.readout,profile()[1])
            self.assertEqual(set(k for k,v in asdict(o.c).items() if v!=asdict(configuration())[k]),set(FIELDS))

    def test_enabled_prefix_future_duplicate_reset(self):
        for theta in (FITTED,CONTROL):
            a,b=factory(theta),factory(theta)
            for i in range(200):
                t=i*.05;ts=(i//2)*.1;z=4+.2*math.sin(ts)
                args=(t,Sample(ts,.2),Sample(ts,z),Sample(ts,z))
                self.assertEqual(a.step(*args),b.step(*args))
            oldused=a.used.copy();d=a.disturbance
            e=a.step(10.,Sample(11.,1.),Sample(11.,15.),Sample(11.,15.))
            self.assertEqual(a.used,oldused);self.assertEqual(a.disturbance,d)
            self.assertTrue(e.command_stale)
            a.reset();self.assertEqual(vars(a),vars(factory(theta)))

    def test_enabled_zero_lock_quarantine_true_stop(self):
        for theta in (FITTED,CONTROL):
            o=factory(theta)
            for i in range(20):
                t=i*.1;o.step(t,Sample(t,0.),Sample(t,1.5),Sample(t,1.5))
            e=o.step(2.,Sample(2.,0.),Sample(2.,0.),Sample(2.,0.))
            self.assertNotEqual(e.mode,'STOPPED')
            self.assertGreater(e.v,.5)
            o=factory(theta)
            for i in range(40):
                t=i*.1;z=4 if i<20 else 9
                e=o.step(t,Sample(t,0.),Sample(t,z),Sample(t,z))
                if 20<=i<34:self.assertNotEqual(e.mode,'REACQUIRING')
            o=factory(theta)
            for i in range(50):
                t=i*.1;e=o.step(t,Sample(t,-.3),Sample(t,0.),Sample(t,0.))
            self.assertEqual(e.mode,'STOPPED');self.assertEqual(e.s,0.)

    def test_enabled_bounded_stream(self):
        for theta in (FITTED,CONTROL):
            o=factory(theta);keys=set(vars(o))
            for i in range(3000):
                t=i*.05;ts=(i//2)*.1;u=.6 if i%800<400 else -.6
                z=3+math.sin(t/5)
                f=None if i%400<100 else Sample(ts,z)
                e=o.step(t,Sample(ts,u),f,f)
                self.assertTrue(all(math.isfinite(v) for v in (e.v,e.s,e.a,e.variance_v,e.variance_s)))
                self.assertLessEqual(abs(e.v),40.);self.assertLessEqual(abs(e.disturbance),.6)
                self.assertEqual(set(vars(o)),keys)

    def test_loader_forbidden_roles_before_io(self):
        s=DevelopmentStore('/does-not-exist')
        for role in ('train','validation','test'):
            with self.assertRaises(PermissionError):s.load(s.plan['splits'][role][0],role)
        with self.assertRaises(PermissionError):s.load(s.plan['splits']['test'][0],'development')

    def test_real_factory_schedule_synthetic_score(self):
        events=[]
        for i in range(401):
            t=i*.1
            events.extend([(t,0,.2),(t,1,4.),(t,2,4.)])
        configs={n:asdict(configuration(x)) for n,x in [('main',None),('candidate',FITTED),('control',CONTROL)]}
        refs={'master':[(i*.05,4.) for i in range(801)],'rover':[]}
        result,a=scored(np.array(events),refs,configs,direct_check=True)
        self.assertTrue(result['direct_baseline_and_feature_off_equal'])
        self.assertEqual(result['receivers']['rover']['candidate']['rmse'],None)
        self.assertTrue(np.array_equal(a['main'][:,0],a['candidate'][:,0]))

    def test_low_speed_requires_nonnegative_command(self):
        events=[]
        for i in range(801):
            t=i*.1;events.extend([(t,0,-.1),(t,1,1.5),(t,2,1.5)])
        self.assertEqual(list(low_speed_windows(np.array(events))),[])
        events=np.array(events);events[events[:,1]==0,2]=0.
        self.assertEqual(len(list(low_speed_windows(events))),2)

    def test_all_v8_statuses_recordable(self):
        self.assertIn('COMMON_MODE_QUARANTINE',STATUS)

import math
if __name__=='__main__':unittest.main()
