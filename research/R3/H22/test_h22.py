"""H22 structural/numerical checks; no measurement DB needed."""
import copy
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
import numpy as np
import data as d
import fit
import evaluation as q

THETA=np.array([1.14,7.8,1.0,.025,.00005,.50,.43])
if os.getenv('H22_CONFIG'):
    THETA=np.array(json.loads(Path(os.environ['H22_CONFIG']).read_text())['theta'])


def scenario(n=401):
    rows=[];f=r=None
    for i in range(n):
        t=i*.05;u=.1 if i<160 else 0. if i<260 else -.1
        v=2.+.04*math.sin(t)
        if i%2==0 and not 210<i<230:f=d.Sample(t-.02,v);r=d.Sample(t-.02,v+.002)
        rows.append((t,(d.Sample(t,u),f,r)))
    return rows


def window(phase='traction'):
    rows=scenario(101);anchor=rows[-1][0]
    ts=anchor+np.arange(1,101)*.05
    return d.Window('synthetic','group',phase,anchor,rows,ts,[d.Sample(float(t),.1) for t in ts],np.full(101,2.))


class H22Checks(unittest.TestCase):
    def test_canonical_profile(self):
        c=d.base_config();self.assertEqual(c.common_mode_quarantine_s,1.5)
        self.assertEqual(c.wheel_time_compensation,0.);self.assertEqual(c.adaptation_tau_s,.5)
        self.assertEqual(d.asdict(d.observer().readout),dict(gain=1.,holdoff_s=.5))
    def test_exact_off_full_state(self):
        base=d.GuardedReadoutObserver(d.base_config(),readout=d.ReadoutConfig(1.,.5));off=d.observer(THETA,enabled=False)
        for t,held in scenario(2001):
            self.assertEqual(base.step(t,*held),off.step(t,*held));self.assertEqual(vars(base),vars(off))
    def test_only_seven_coefficients(self):
        b,c=d.asdict(d.base_config()),d.asdict(d.config_for(THETA))
        self.assertTrue(all(c[k]==b[k] for k in b if k not in d.PHYSICAL))
    def test_baseline_theta_exact(self):
        self.assertEqual(d.asdict(d.config_for(d.THETA0)),d.asdict(d.base_config()))
    def test_bounds(self):
        for x in [np.zeros(7),np.full(7,np.nan),np.zeros(6),d.HIGH+1]:
            with self.assertRaises(ValueError):d.config_for(x)
    def test_robust_residual(self):
        x=np.array([0.,1e-12,-1e-8,-.5,3.,100.])
        np.testing.assert_allclose(fit.robust_residual(x)**2,fit.rho(x),atol=1e-14)
    def test_integral_scaling_and_bias(self):
        np.testing.assert_array_equal(fit.SIGMA_S,d.HORIZONS*d.SIGMA)
        w=window();w.target=np.full(101,1.5)
        e=np.full(101,.2);prefix=np.cumsum(.5*(e[1:]+e[:-1])*.05)
        np.testing.assert_allclose(prefix[d.HINDEX],.2*d.HORIZONS,atol=1e-14)
    def test_full_rollout_parity(self):
        ws=[window('traction'),window('coast'),window('braking')]
        for theta in [d.THETA0,THETA]:
            np.testing.assert_allclose(d.predict_windows(theta,ws),np.stack([d.original_rollout(theta,w) for w in ws]),atol=1e-10,rtol=0)
    def test_no_target_teacher_forcing(self):
        w=window();p=d.predict_windows(THETA,[w]);other=copy.deepcopy(w);other.target[:]=38.
        np.testing.assert_array_equal(p,d.predict_windows(THETA,[other]))
    def test_future_target_not_initialization(self):
        w=window();p=d.warm_states(THETA,[w]);w.target[1:]=1000.
        np.testing.assert_array_equal(p,d.warm_states(THETA,[w]))
    def test_budget_hard_counter(self):
        b=fit.Budget(2);b.charge();b.charge()
        with self.assertRaises(fit.BudgetExceeded):b.charge()
        self.assertEqual(b.used,2)
    def test_prefix_causality(self):
        rows=scenario();a=d.observer(THETA);prefix=[a.step(t,*h) for t,h in rows[:150]]
        b=d.observer(THETA);whole=[b.step(t,*h) for t,h in rows]
        self.assertEqual(prefix,whole[:150])
    def test_stale_future_duplicate(self):
        for theta in [d.THETA0,THETA]:
            o=d.observer(theta);o.reset(velocity=2.)
            s=d.Sample(0.,2.);o.step(0.,d.Sample(0.,0.),s,s)
            e=o.step(.05,d.Sample(.05,0.),s,s)
            self.assertEqual(e.front_status,'DUPLICATE_OR_OLD')
            e=o.step(.1,d.Sample(.1,0.),d.Sample(.2,2.),d.Sample(.2,2.))
            self.assertEqual(e.front_status,'MISSING_OR_STALE')
            e=o.step(.3,d.Sample(.3,0.),s,s)
            self.assertEqual(e.front_status,'MISSING_OR_STALE')
    def test_reset_bounded_state(self):
        o=d.observer(THETA);initial=set(vars(o));max_lists={}
        for t,h in scenario(2001):
            e=o.step(t,*h);self.assertTrue(all(math.isfinite(x) for x in [e.v,e.s,e.variance_v,e.variance_s]))
            self.assertEqual(set(vars(o)),initial)
            for k,v in vars(o).items():
                if isinstance(v,list):self.assertLessEqual(len(v),2)
        o.reset();self.assertEqual(vars(o),vars(d.observer(THETA)))
    def test_distance_velocity_consistency(self):
        o=d.observer(THETA);old=None
        for t,h in scenario():
            e=o.step(t,*h)
            if old is not None and e.mode not in ('INITIALIZED','WAITING_FOR_INITIALIZATION'):
                self.assertAlmostEqual(e.s-old.s,.5*(old.v+e.v)*(e.t-old.t),places=10)
            old=e
    def test_role_rejection_before_io(self):
        s=d.Store()
        for role in ['validation','test']:
            with self.assertRaises(PermissionError):s.load(s.plan['splits'][role][0],role)
    def test_zero_lock_guard(self):
        o=d.observer(THETA);o.reset(velocity=1.5)
        for i in range(21):
            t=i*.05;e=o.step(t,d.Sample(t,0.),d.Sample(t,0.),d.Sample(t,0.))
            self.assertNotEqual(e.mode,'STOPPED');self.assertGreater(e.v,.25)
    def test_common_jump_quarantine(self):
        o=d.observer(THETA);o.reset(velocity=3.)
        for i in range(5):
            t=i*.05;v=3. if i<2 else 8.
            o.step(t,d.Sample(t,0.),d.Sample(t,v),d.Sample(t,v))
        self.assertGreater(o.reacquire_blocked_until,.2)
    def test_paired_baseline_driver(self):
        events=[];refs={'master':[],'rover':[]}
        for t,h in scenario(301):
            for ch,s in enumerate(h):
                if s is not None:events.append([s.t,ch,s.value])
            refs['master'].append([t,2.])
        events=np.array(events)
        row,arrays,_=q.paired(events,refs,THETA);q.assert_baseline(events,refs,row)
        off,_,_=q.paired(events,refs,d.THETA0)
        self.assertEqual(off['receivers']['master']['main']['rmse'],off['receivers']['master']['candidate']['rmse'])
    def test_worst_penalty_and_group_weights(self):
        ws=[window(),window('coast')];ws[1].group='other'
        e=np.ones((2,3))*.1;s=np.ones((2,3))*.1
        loss,cells=fit.loss_components(e,s,ws)
        same,_=fit.loss_components(e,s,ws,cells)
        self.assertAlmostEqual(same['smooth_worst_regression'],.1*np.log(2.))
        worse,_=fit.loss_components(e*2,s*2,ws,cells)
        self.assertGreater(worse['smooth_worst_regression'],same['smooth_worst_regression'])

if __name__=='__main__':unittest.main(verbosity=2)
