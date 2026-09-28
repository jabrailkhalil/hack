"""Independent linear oracle and runtime invariants. No accuracy dataset IO."""
from pathlib import Path
import copy, dataclasses, math, random, sys, unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import common as cm
from factory import candidate, NativeTimeObserver, M
from joint import JointHistory

def normal(x):
    if dataclasses.is_dataclass(x):return dataclasses.asdict(x)
    if isinstance(x,dict):return {k:normal(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)):return [normal(v) for v in x]
    return x

def assert_same(test, a,b):
    for k,v in vars(a).items():test.assertEqual(normal(v),normal(getattr(b,k)),k)

def stream(n=400):
    held=None
    for i in range(n):
        t=i*.05
        command=cm.Sample(t,.2 if i<n/2 else -.15)
        if i%2==0:held=cm.Sample(t-.075 if i>=2 else t,3.+.1*math.sin(t))
        yield t,command,held,held

def gaussian_batch(times,observations,v0=2.,p0=.7,q=.13,a=.4):
    t=np.asarray(times);m=v0+a*t;p=p0+q*np.minimum.outer(t,t)
    if observations:
        tau=np.array([x[0] for x in observations]);z=np.array([x[1] for x in observations]);r=np.array([x[2] for x in observations])
        cross=p0+q*np.minimum.outer(t,tau)
        cov=p0+q*np.minimum.outer(tau,tau)+np.diag(r)
        gain=np.linalg.solve(cov,cross.T).T
        return m+gain@(z-v0-a*tau),p-gain@cross.T
    return m,p

class JointTests(unittest.TestCase):
    def test_random_delays_against_batch_and_chronological(self):
        rng=random.Random(3001)
        for case in range(30):
            b=JointHistory(0,2,.7,window=1.)
            for t in (.08,.2,.4):b.append(t,b.means[-1]+.4*(t-b.times[-1]),.13)
            times=rng.sample([i/1000 for i in range(1,399)],12)
            observations=[]
            for num,t in enumerate(times):
                z=2+.4*t+rng.gauss(0,.12);r=.02+.03*rng.random()
                i=b.index(t);self.assertIsNotNone(i)
                b.observe(i,z,r,(case,num));observations.append((t,z,r))
                m,p=gaussian_batch(b.times,observations)
                np.testing.assert_allclose(b.means,m,rtol=0,atol=1e-9)
                np.testing.assert_allclose(b.p,p,rtol=0,atol=1e-9)
                self.assertGreaterEqual(np.linalg.eigvalsh(b.p).min(),-1e-10)
                # A separately implemented chronological scalar Kalman filter.
                mu,pv,old=2.,.7,0.
                for tau,value,noise in sorted(observations):
                    mu+=.4*(tau-old);pv+=.13*(tau-old);k=pv/(pv+noise)
                    mu+=k*(value-mu);pv=(1-k)**2*pv+k*k*noise;old=tau
                mu+=.4*(.4-old);pv+=.13*(.4-old)
                self.assertAlmostEqual(b.means[-1],mu,places=10)
                self.assertAlmostEqual(b.p[-1][-1],pv,places=10)
    def test_zero_age_scalar(self):
        b=JointHistory(0,1,.3);b.append(.1,1.2,.1)
        k=.31/(.31+.04);v,p=b.observe(1,1.5,.04,'x')
        self.assertAlmostEqual(v,1.2+k*.3);self.assertAlmostEqual(p,(1-k)*.31)
    def test_duplicate_does_not_change_mean_or_cov(self):
        b=JointHistory(0,1,.1);b.observe(0,1.1,.02,'a');saved=copy.deepcopy(vars(b))
        with self.assertRaises(ValueError):b.observe(0,1.1,.02,'a')
        self.assertEqual(vars(b),saved)
    def test_outside_history(self):
        b=JointHistory(0,1,.1);b.append(.1,1,.1)
        self.assertIsNone(b.index(-.001));self.assertIsNone(b.index(.10001));self.assertIsNone(b.index(float('nan')))
    def test_state_bound_and_pruning(self):
        b=JointHistory(0,1,.1)
        for j in range(1,1001):
            t=j*.002;b.append(t,1,.1)
            if j%2:b.observe(len(b.times)-1,1,.1,j)
            self.assertLessEqual(len(b.times),32);self.assertLessEqual(len(b.events),64)
            self.assertGreaterEqual(b.times[0],t-.25-1e-9)
            self.assertEqual(len(b.q),len(b.times)-1)
            self.assertTrue(all(len(row)==len(b.times) for row in b.p))
    def test_full_state_insertion_refused(self):
        b=JointHistory(0,1,.1)
        for j in range(1,32):b.append(j*.001,1,.1)
        self.assertIsNone(b.index(.0005));self.assertEqual(len(b.times),32)
    def test_ledger_capacity(self):
        b=JointHistory(0,1,.1)
        for j in range(64):b.observe(0,1,.1,j)
        before=copy.deepcopy(vars(b))
        with self.assertRaises(ValueError):b.observe(0,1,.1,64)
        self.assertEqual(vars(b),before)
    def test_invalid_parameters_and_noise(self):
        for args in [(0,1,0),(0,float('nan'),1),(0,1,-1)]:
            with self.assertRaises(ValueError):JointHistory(*args)
        b=JointHistory(0,1,.1)
        for r in (0,-1,float('nan')):
            with self.assertRaises(ValueError):b.observe(0,1,r,'a')
    def test_piecewise_q_bridge(self):
        b=JointHistory(0,2,.7,1);b.append(.1,2.1,.1);b.append(.2,2.3,.4)
        i=b.index(.15)
        self.assertAlmostEqual(b.means[i],2.2);self.assertAlmostEqual(b.p[i][i],.73)
        np.testing.assert_allclose(b.q,[.1,.4,.4],rtol=0,atol=1e-15)
    def test_prefix_invariance(self):
        def run(n):
            b=JointHistory(0,1,.1);out=[]
            for j in range(1,n):
                t=j*.05;b.append(t,b.means[-1]+.01,.1)
                i=b.index(t-.025);b.observe(i,1+.01*j,.1,j)
                out.append((b.means[-1],b.p[-1][-1]))
            return out
        self.assertEqual(run(200)[:99],run(100))

class RuntimeTests(unittest.TestCase):
    def test_feature_off_whole_v8_exact(self):
        base,off=cm.baseline(),candidate(False)
        for i,args in enumerate(stream(1200)):
            t,c,f,r=args
            if 200<=i<220:f=r=None
            if 400<=i<425:f=r=cm.Sample(t,0.)
            if 600<=i<620:f=r=cm.Sample(t,8.)
            self.assertEqual(normal(base.step(t,c,f,r)),normal(off.step(t,c,f,r)))
            assert_same(self,base,off)
    def test_zero_age_whole_v8_exact(self):
        base,on=cm.baseline(),candidate()
        for i in range(200):
            t=i*.05;c=cm.Sample(t,.2);w=cm.Sample(t,3+.01*i)
            self.assertEqual(normal(base.step(t,c,w,w)),normal(on.step(t,c,w,w)))
            assert_same(self,base,on)
    def test_native_activates_and_psd(self):
        on=candidate()
        for args in stream():
            e=on.step(*args)
            self.assertTrue(math.isfinite(e.v))
            if on._h30_bank:
                self.assertGreaterEqual(np.linalg.eigvalsh(on._h30_bank.p).min(),-1e-10)
                self.assertLessEqual(len(on._h30_inputs)+len(on._h30_bank.events),64)
                self.assertEqual(len(on._h30_bank.times),len(on._h30_bank.p))
        self.assertGreater(on._h30_stats['native_updates'],100)
        self.assertGreater(on._h30_stats['material_updates'],100)
        self.assertGreater(on._h30_stats['past_tick_updates'],100)
    def test_no_double_readout_or_distance_reset(self):
        on=candidate();old=None;integral=0;native=0
        for i,args in enumerate(stream(500)):
            t,c,f,r=args
            if 200<=i<220:f=r=None
            e=on.step(t,c,f,r)
            if old is not None and e.mode!='INITIALIZED':integral+=.5*(old.v+e.v)*(e.t-old.t)
            if e.mode=='INITIALIZED':integral=e.s
            self.assertAlmostEqual(e.s,integral,places=9)
            if on._h30_native and on._h30_skip_readout:
                self.assertEqual(on._velocity_correction,0.);native+=1
            old=e
        self.assertGreater(native,100)
    def test_no_retroactive_output_mutation(self):
        on=candidate();saved=[]
        for args in stream(100):
            e=on.step(*args);saved.append((e,normal(e)))
        for e,expected in saved:self.assertEqual(normal(e),expected)
    def test_repeated_input_not_relearned(self):
        on=candidate();args=list(stream(6))
        for arg in args[:-1]:on.step(*arg)
        n=on._h30_stats['native_updates'];d=on.disturbance;prev=normal(on.adapt_previous)
        on.step(*args[-1])
        self.assertEqual(on._h30_stats['native_updates'],n)
        self.assertEqual(on.disturbance,d);self.assertEqual(normal(on.adapt_previous),prev)
    def test_original_adaptation_once(self):
        on=candidate();orig=M.core.Observer.step
        # Observe each unique pair: verify exact existing EMA formula, not replay.
        verified=0
        for args in stream(100):
            t,c,f,r=args;d0=on.disturbance;old=on.adapt_previous
            e=on.step(*args)
            if e.mode=='FUSED' and old is not None and .05<=f.t-old.t<=on.c.max_age_s and abs(f.value)>.5:
                a=(f.value-old.value)/(f.t-old.t)
                if abs(a)<=on.c.max_accel_mps2:
                    desired=a-on.drive_a+on.resistance(on.v)
                    w=1-math.exp(-(f.t-old.t)/on.c.adaptation_tau_s)
                    expected=max(-on.c.disturbance_limit_mps2,min(on.c.disturbance_limit_mps2,d0+w*(desired-d0)))
                    self.assertEqual(on.disturbance,expected);verified+=1
        self.assertGreater(verified,20)
    def test_causal_prefix(self):
        def run(n):
            on=candidate();return [normal(on.step(*a)) for a in stream(600)][:n] # fixed prefix commands
        on=candidate();short=[normal(on.step(*a)) for a in list(stream(600))[:200]]
        self.assertEqual(run(200),short)
    def test_reset_exact_off(self):
        b,o=cm.baseline(),candidate(False)
        for args in stream(100):b.step(*args);o.step(*args)
        b.reset(velocity=2,position=3);o.reset(velocity=2,position=3);assert_same(self,b,o)
        self.assertEqual(o._h30_inputs.__len__(),0)
    def test_stale_future_and_nonfinite(self):
        for wheel in (None,cm.Sample(-1,3),cm.Sample(10,3),cm.Sample(float('nan'),3),cm.Sample(0,float('nan'))):
            on=candidate();on.reset(velocity=3)
            e=on.step(0,cm.Sample(1,.2),wheel,wheel)
            self.assertTrue(e.command_stale);self.assertFalse(on._h30_native)
            self.assertTrue(math.isfinite(e.v))
    def test_raw_hard_rejection_no_native(self):
        on=candidate()
        for args in stream(20):on.step(*args)
        e=on.step(1.,cm.Sample(1.,.2),cm.Sample(.99,20),cm.Sample(.99,20))
        self.assertFalse(on._h30_native)
        self.assertIn(e.front_status,('RATE_ANOMALY','MODEL_DISAGREEMENT'))
    def test_zero_lock_preserved(self):
        on=candidate();on.reset(velocity=1.5)
        for i in range(12):
            t=i*.05;e=on.step(t,cm.Sample(t,.3),cm.Sample(t,0),cm.Sample(t,0))
            self.assertNotEqual(e.mode,'STOPPED');self.assertFalse(on._h30_native)
    def test_quarantine_preserved(self):
        on=candidate()
        for i in range(5):
            t=i*.1;on.step(t,cm.Sample(t,.2),cm.Sample(t,3),cm.Sample(t,3))
        t=.5;e=on.step(t,cm.Sample(t,.2),cm.Sample(t,8),cm.Sample(t,8))
        self.assertFalse(on._h30_native)
        self.assertGreater(on.reacquire_blocked_until,t)
    def test_event_source_retention(self):
        on=candidate()
        for args in stream(200):
            e=on.step(*args)
            self.assertTrue(all(x[1]>=e.t-on.c.max_age_s-1e-9 for x in on._h30_inputs))
            self.assertLessEqual(len(on._h30_inputs),64)
    def test_input_api_and_no_heavy_runtime_import(self):
        import ast,inspect
        from factory import sources
        self.assertEqual(list(inspect.signature(NativeTimeObserver.step).parameters),['self','t','command','front','rear'])
        for file in ('factory.py','joint.py'):
            text=(Path(__file__).resolve().parents[1]/file).read_text()
            modules=[n.module for n in ast.walk(ast.parse(text)) if isinstance(n,ast.ImportFrom)]
            modules += [a.name for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Import) for a in n.names]
            self.assertFalse(any(m and m.split('.')[0] in ('numpy','scipy','sqlite3') for m in modules))
if __name__=='__main__':unittest.main()
