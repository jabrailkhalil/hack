import math
import unittest
from dataclasses import asdict
from model import *
from foundation import metadata, prepared


class H36Tests(unittest.TestCase):
    def test_scalar_integral_parity(self):
        c,_=profile();o=GuardedReadoutObserver(c)
        t=np.arange(201)*DT;u=(.4*np.sin(t))[None,:];v=(5+.1*np.sin(t))[None,:]
        a=[];drive=0.
        for k in range(1,201):
            target=o.drive_target(float(u[0,k]),float(v[0,k-1]))
            drive+=(1-math.exp(-DT/c.actuator_tau_s))*(target-drive)
            a.append(max(-3.,min(3.,drive-o.resistance(float(v[0,k-1])))))
        expected=(np.array(a[100:])*DT).reshape(10,10).sum(axis=1)
        np.testing.assert_allclose(physical(theta0(),u,v)[0],expected,atol=1e-14,rtol=0)

    def test_causal_actuator_warmup(self):
        u=np.full((1,201),.3);v=np.full_like(u,6.)
        _,a=physical(theta0(),u,v,return_drive=True)
        u[:,101:]=-.8;v[:,101:]=30
        _,b=physical(theta0(),u,v,return_drive=True)
        np.testing.assert_array_equal(a,b)

    def test_constant_offset_invariance(self):
        error=np.array([[.01,-.02,.03,-.01]*3,[.02,-.01,.01,-.03]*3])
        offset=.2
        b=profile_load(error);shifted=profile_load(error-BIN*offset)
        np.testing.assert_allclose(shifted,b+offset,atol=1e-14,rtol=0)
        np.testing.assert_allclose(error+BIN*b[:,None],error-BIN*offset+BIN*shifted[:,None],atol=1e-14)

    def test_quadratic_projection(self):
        h=np.array([.3,.5,.8]);y=np.array([.1,.6,-.3]);f=np.array([.01,.1,.05])
        b=np.dot(h,y-f)/np.dot(h,h)
        P=np.eye(3)-np.outer(h,h)/np.dot(h,h)
        np.testing.assert_allclose(f+h*b-y,P@(f-y),atol=1e-14)
        np.testing.assert_allclose(P@h,0,atol=1e-14)

    def test_changing_load_not_removed(self):
        # Within a valid additive model, a changing load is not a constant b.
        error=BIN*np.linspace(-.25,.25,10)[None,:]
        b=profile_load(error)
        self.assertLess(abs(b[0]),1e-14)
        self.assertGreater(np.sqrt(np.mean((error+BIN*b[:,None])**2)),.05)

    def test_kkt_and_bound(self):
        rng=np.random.default_rng(36);error=rng.normal(0,.15,(100,10))
        b=profile_load(error);r=(error+BIN*b[:,None])/(math.sqrt(2)*.1)
        self.assertLess(np.max(abs(np.sum(r/np.hypot(1,r),axis=1))),1e-12)
        np.testing.assert_allclose(profile_load(np.full((2,10),2.)),[-.6,-.6])
        np.testing.assert_allclose(profile_load(np.full((2,10),-2.)),[.6,.6])

    def test_no_excitation_projection_rank_failure(self):
        data=dict(u=np.zeros((12,201)),v=np.full((12,201),5.),y=np.zeros((12,10)),
                  meta=[dict(group=str(i%4),phase=('coast','traction','braking')[i%3]) for i in range(12)])
        self.assertFalse(rank_report(theta0(),data)['passed'])

    def test_only_three_model_fields_change(self):
        a=asdict(configuration());b=asdict(configuration(theta0()*1.05))
        self.assertEqual({k for k in a if a[k]!=b[k]},set(FIELDS))
        self.assertFalse(any('window' in k or 'load' in k for k in b))

    def test_feature_off_full_v8(self):
        a=factory();b=factory([1.,8.,1.],enabled=False)
        from reserve_odometry.core import Sample
        for i in range(2000):
            if i==1000:a.reset();b.reset()
            t=(i%1000)*.05;stamp=(i%1000//2)*.1
            v=4. if i%250<200 else 9.
            front=None if i%150<10 else Sample(stamp,v)
            rear=Sample(stamp,v)
            args=(t,Sample(stamp,.1),front,rear)
            self.assertEqual(a.step(*args),b.step(*args))
            self.assertEqual(vars(a),vars(b))

    def test_role_before_io(self):
        s=ev.ex.Store('/nonexistent')
        for role in ('validation','test','development'):
            bag=s.plan['splits']['test'][0]
            with self.assertRaises(PermissionError):s.load(bag,role)

    def test_group_partition_deterministic(self):
        a=metadata();self.assertEqual(a,metadata())
        self.assertEqual(len(a['check']),7);self.assertFalse(set(a['check'])&set(a['fitting']))
        self.assertEqual(len(a['fitting']),20)

    def test_robust_transform_identity(self):
        r=np.array([0,1e-14,.1,1.,-3.,1e4])
        np.testing.assert_allclose(transformed(r)**2,2*r*r/(np.hypot(1,r)+1),rtol=1e-14,atol=1e-28)

    def test_equal_group_phase_weights(self):
        m=[dict(group='a',phase='coast')]*10+[dict(group='b',phase='coast'),dict(group='b',phase='traction')]
        w=weights(m);self.assertAlmostEqual(w[:10].sum(),.5)
        self.assertAlmostEqual(w[10],.25);self.assertAlmostEqual(w.sum(),1.)

    def test_invalid_inputs(self):
        for x in ([0,3,1],[1,101,1],[np.nan,5,1]):
            with self.assertRaises(ValueError):configuration(x)
        with self.assertRaises(ValueError):profile_load(np.array([[np.nan]]))
        with self.assertRaises(ValueError):profile_load(np.zeros((2,0)))


if __name__=='__main__':unittest.main()
