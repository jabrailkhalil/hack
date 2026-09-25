import math
import random
import unittest
from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.route import Route


class ObserverTests(unittest.TestCase):
    def test_config_validation(self):
        for kw in ({'mass_kg': 0}, {'wheel_sigma_mps': -1}, {'max_age_s': float('nan')},
                   {'efficiency': 1.1}, {'command_deadband': 1}, {'travel_direction': 0}):
            with self.assertRaises(ValueError):
                Config(**kw)

    def test_waits_for_two_wheels(self):
        o = Observer()
        e = o.step(0, Sample(0, 0), Sample(0, 4), None)
        self.assertEqual(e.mode, 'WAITING_FOR_INITIALIZATION')
        e = o.step(.02, Sample(.02, 0), Sample(.02, 4), Sample(.02, 4))
        self.assertEqual(e.v, 4)

    def test_constant_speed(self):
        o = Observer()
        for i in range(501):
            t = i * .02
            e = o.step(t, Sample(t, .1), Sample(t, 5), Sample(t, 5))
        self.assertLess(abs(e.v - 5), .06)
        self.assertLess(abs(e.s - 50), .5)

    def test_stationary_and_no_creep(self):
        o = Observer()
        for i in range(501):
            t = i * .02
            # sensor rate 10 Hz, output rate 50 Hz
            ts = (i // 5) * .1
            e = o.step(t, Sample(ts, -.5), Sample(ts, 0), Sample(ts, 0))
        self.assertEqual(e.mode, 'STOPPED')
        self.assertEqual(e.s, 0)
        self.assertEqual(e.v, 0)

    def test_no_repeated_measurement_update(self):
        o = Observer(); o.step(0, Sample(0, 0), Sample(0, 4), Sample(0, 4))
        p = o.pv
        for i in range(1, 8):
            t = i * .02
            e = o.step(t, Sample(0, 0), Sample(0, 4), Sample(0, 4))
        self.assertGreater(e.variance_v, p)
        self.assertEqual(e.front_status, 'DUPLICATE_OR_OLD')

    def test_future_sample_not_consumed(self):
        o = Observer(); o.reset(velocity=4)
        e = o.step(0, Sample(1, 0), Sample(.1, 4), Sample(.1, 4))
        self.assertTrue(e.command_stale)
        self.assertEqual(o.used, [None, None])
        e = o.step(.1, Sample(.1, 0), Sample(.1, 4), Sample(.1, 4))
        self.assertEqual(e.mode, 'FUSED')

    def test_nan_and_range_are_ignored(self):
        for x in (float('nan'), float('inf'), 1000):
            o = Observer(); o.reset(velocity=5)
            e = o.step(0, Sample(0, float('nan')), Sample(0, x), Sample(0, 5))
            self.assertTrue(math.isfinite(e.v))
            self.assertEqual(e.mode, 'SINGLE_WHEEL')

    def test_single_wheel_slip_and_recovery(self):
        o = Observer()
        errors = []
        for i in range(751):
            t = i * .02
            f = 13 if 3 < t < 8 else 5
            e = o.step(t, Sample(t, .1), Sample(t, f), Sample(t, 5))
            errors.append(abs(e.v - 5))
        self.assertLess(max(errors), .12)
        self.assertEqual(e.mode, 'FUSED')

    def test_simultaneous_spike(self):
        o = Observer()
        for i in range(101):
            t = i * .02
            z = 15 if i == 70 else 5
            e = o.step(t, Sample(t, .1), Sample(t, z), Sample(t, z))
            self.assertLess(abs(e.v - 5), .2)

    def test_short_common_mode_offset_does_not_reacquire(self):
        o = Observer()
        for i in range(101):
            t = i * .02
            z = 10 if 1.0 <= t < 1.6 else 5
            e = o.step(t, Sample(t, 0), Sample(t, z), Sample(t, z))
        self.assertLess(abs(e.v - 5), .2)
        self.assertNotEqual(e.mode, 'REACQUIRING')

    def test_common_mode_jump_quarantine_blocks_short_false_pair(self):
        o=Observer(Config(common_mode_quarantine_s=1.5))
        modes=[]; errors=[]
        for i in range(251):
            t=i*.02
            z=10 if 2.0 <= t < 3.2 else 5
            e=o.step(t,Sample(t,0),Sample(t,z),Sample(t,z))
            modes.append(e.mode);errors.append(abs(e.v-5))
        self.assertNotIn('REACQUIRING',modes)
        self.assertLess(max(errors),.25)
        self.assertGreaterEqual(o.reacquire_blocked_until,3.5)

    def test_quarantine_does_not_delay_return_after_long_dropout(self):
        base=Observer(Config(common_mode_quarantine_s=0))
        guarded=Observer(Config(common_mode_quarantine_s=1.5))
        first={}
        for i in range(301):
            t=i*.02
            if t < 1:
                z=5; front=rear=Sample(t,z)
            elif t < 2:
                front=rear=None
            else:
                # Returning pair is far from the model but prior raw samples are
                # older than max_age_s, therefore no RATE_ANOMALY quarantine.
                z=8; front=rear=Sample(t,z)
            for name,o in (('base',base),('guarded',guarded)):
                e=o.step(t,Sample(t,0),front,rear)
                if e.mode=='REACQUIRING' and name not in first:first[name]=t
        self.assertIn('base',first);self.assertIn('guarded',first)
        self.assertAlmostEqual(first['guarded'],first['base'],places=8)

    def test_quarantine_disabled_preserves_state_shape_and_behavior(self):
        c=Config(common_mode_quarantine_s=0)
        o=Observer(c)
        self.assertEqual(o.reacquire_blocked_until,-math.inf)
        for i in range(51):
            t=i*.02
            e=o.step(t,Sample(t,0),Sample(t,5),Sample(t,5))
        self.assertLess(abs(e.v-5),.01)
        self.assertEqual(o.rate_anomaly_times,[None,None])

    def test_persistent_agreeing_pair_reacquires_after_model_divergence(self):
        o = Observer()
        modes = []
        for i in range(401):
            t = i * .02
            z = 5 if t < 1.0 else 10
            e = o.step(t, Sample(t, 0), Sample(t, z), Sample(t, z))
            modes.append(e.mode)
        self.assertIn('REACQUIRING', modes)
        self.assertGreater(e.v, 9.5)
        self.assertIn(e.mode, ('FUSED', 'REACQUIRING'))

    def test_locked_common_zero_pair_never_reacquires_moving_state(self):
        o = Observer()
        for i in range(51):
            t = i * .02
            e = o.step(t, Sample(t, 0), Sample(t, 10), Sample(t, 10))
        for i in range(51, 251):
            t = i * .02
            e = o.step(t, Sample(t, -.8), Sample(t, 0), Sample(t, 0))
            self.assertNotEqual(e.mode, 'REACQUIRING')
        self.assertGreater(e.v, 4)

    def test_locked_wheels_not_zero_velocity_update(self):
        o = Observer()
        o.step(0, Sample(0, 0), Sample(0, 10), Sample(0, 10))
        for i in range(1, 51):
            t = i * .02
            e = o.step(t, Sample(t, -.6), Sample(t, 0), Sample(t, 0))
        self.assertGreater(e.v, 8)
        self.assertNotEqual(e.mode, 'STOPPED')

    def test_persistent_zero_pair_cannot_stop_slow_moving_model(self):
        o=Observer();o.reset(velocity=1.0)
        for i in range(21):
            t=i*.05;e=o.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
            self.assertNotEqual(e.mode,'STOPPED');self.assertEqual(e.front_status,'ZERO_LOCK_SUSPECT');self.assertEqual(e.rear_status,'ZERO_LOCK_SUSPECT')
        self.assertGreater(e.v,.9)

    def test_true_stop_still_acquired_after_model_braking(self):
        o=Observer();o.reset(velocity=1.0)
        for i in range(81):
            t=i*.05;e=o.step(t,Sample(t,-1),Sample(t,0),Sample(t,0))
        self.assertEqual(e.mode,'STOPPED');self.assertEqual(e.v,0)

    def test_alternating_zero_wheels_cannot_stop_moving_model(self):
        o=Observer();f=r=Sample(0,1.3)
        for i in range(61):
            t=i*.05;s=Sample(t,1.3 if t<1 else 0)
            if i%2:f=s
            else:r=s
            e=o.step(t,Sample(t,0),f,r);self.assertNotEqual(e.mode,'STOPPED')
        self.assertGreater(e.v,1.)

    def test_single_zero_wheel_does_not_veto_other_wheel(self):
        o=Observer();o.reset(velocity=1.0)
        for i in range(21):
            t=i*.05;e=o.step(t,Sample(t,0),Sample(t,0),Sample(t,1))
            self.assertNotEqual(e.rear_status,'ZERO_LOCK_SUSPECT')
        self.assertGreater(e.v,.9)

    def test_dropouts_remain_finite_with_uncertainty_growth(self):
        o = Observer(); o.reset(velocity=5)
        for i in range(501):
            t = i * .02
            e = o.step(t)
        self.assertTrue(all(math.isfinite(x) for x in (e.s, e.v, e.a)))
        self.assertGreater(e.variance_v, 1)
        self.assertGreater(e.variance_s, 1)
        self.assertEqual(e.mode, 'MODEL_ONLY')

    def test_dropout_duration_matrix_recovers(self):
        for duration in (0.1, 0.5, 2.0, 5.0, 10.0):
            for missing in ('front', 'both'):
                with self.subTest(duration=duration, missing=missing):
                    o = Observer()
                    t = 0.0
                    while t <= 1.0 + 1e-9:
                        o.step(t, Sample(t, 0), Sample(t, 5), Sample(t, 5))
                        t += .02
                    end = t + duration
                    while t < end - 1e-9:
                        front = None if missing in ('front', 'both') else Sample(t, 5)
                        rear = None if missing == 'both' else Sample(t, 5)
                        e = o.step(t, Sample(t, 0), front, rear)
                        self.assertTrue(math.isfinite(e.v))
                        t += .02
                    recovery_end = t + 3.0
                    while t < recovery_end - 1e-9:
                        e = o.step(t, Sample(t, 0), Sample(t, 5), Sample(t, 5))
                        t += .02
                    self.assertLess(abs(e.v - 5), .1)
                    self.assertGreater(e.s, 4.0 * duration)

    def test_time_errors_require_reset(self):
        o = Observer(); o.step(5)
        for t in (5, 4, 7, float('nan')):
            with self.assertRaises(ValueError):
                o.step(t)
        o.reset(); o.step(0)

    def test_disturbance_frozen_during_bad_data(self):
        o = Observer(); o.reset(velocity=5); o.disturbance = .2
        for i in range(10):
            e = o.step(i * .02, Sample(i * .02, .1))
        self.assertEqual(e.disturbance, .2)

    def test_drive_nonlinearity_and_braking(self):
        o = Observer()
        self.assertEqual(o.drive_target(0, 5), 0)
        self.assertLess(o.drive_target(-.5, 5), 0)
        self.assertGreater(o.drive_target(-.5, -5), 0)
        self.assertGreater(o.drive_target(.8, 2), o.drive_target(.8, 30))

    def test_signed_velocity(self):
        o = Observer(Config(travel_direction=-1))
        for i in range(101):
            t = i * .02
            e = o.step(t, Sample(t, .1), Sample(t, -4), Sample(t, -4))
        self.assertLess(e.s, -7.8)
        self.assertLess(e.v, 0)

    def test_per_sensor_monotonicity(self):
        o = Observer(); o.reset(velocity=4)
        o.step(1, Sample(1, 0), Sample(1, 4), Sample(1, 4))
        e = o.step(1.02, Sample(1, 0), Sample(.99, 20), Sample(1.02, 4))
        self.assertEqual(e.front_status, 'DUPLICATE_OR_OLD')


class RouteTests(unittest.TestCase):
    def test_arc_interpolation(self):
        r = Route([(0,0,0), (10,0,0), (10,10,0)])
        xyz, q = r.at(15)
        self.assertEqual(xyz, (10,5,0))
        self.assertAlmostEqual(sum(x*x for x in q), 1)
        self.assertAlmostEqual(q[2], math.sqrt(.5))

    def test_degenerate_and_boundary(self):
        with self.assertRaises(ValueError): Route([(0,0,0), (0,0,0)])
        r = Route([(0,0,0), (10,0,0)])
        for s in (-1, 11, float('nan')):
            with self.assertRaises(ValueError): r.at(s)
        self.assertEqual(r.at(10)[0], (10,0,0))


if __name__ == '__main__':
    unittest.main()
