import unittest,sys,math,random,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from foundation import api,WORK,Timeline,Sample,cfg,readout,Observer,InstrumentedObserver,clean_instrument,suffix
from instrument import COLUMNS,dynamical_state

class InstrumentTests(unittest.TestCase):
    def pair(self):return Observer(cfg,readout=readout),InstrumentedObserver(cfg,readout=readout)
    def compare(self,seq):
        a,b=self.pair()
        for args in seq:
            self.assertEqual(a.step(*args),b.step(*args))
            for k,v in vars(a).items():self.assertEqual(v,getattr(b,k),k)
        return b
    def seq(self,modify=None,n=200):
        for i in range(n):
            t=i*.05;f=r=Sample(t-.025,3+.01*math.sin(t));u=Sample(t,.1)
            if modify:f,r=modify(i,t,f,r)
            yield t,u,f,r
    def test_plain_exact(self):self.compare(self.seq(n=2000))
    def test_one_good_then_bad(self):
        b=self.compare(self.seq(lambda i,t,f,r:(f,r) if i in (0,1,22) else (Sample(t,15),Sample(t,15)),n=40))
        self.assertFalse(b.diag[10])
    def test_alternating_good_bad(self):
        b=self.compare(self.seq(lambda i,t,f,r:(f,r) if i%2==0 else (None,None),n=200))
        self.assertFalse(b.diag[10])
    def test_stale(self):self.compare(self.seq(lambda i,t,f,r:(Sample(t-1,3),Sample(t-1,3))))
    def test_future(self):self.compare(self.seq(lambda i,t,f,r:(Sample(t+1,3),Sample(t+1,3))))
    def test_duplicate(self):self.compare(self.seq(lambda i,t,f,r:(Sample(0,3),Sample(0,3))))
    def test_common_bias(self):self.compare(self.seq(lambda i,t,f,r:(Sample(t,4),Sample(t,4)) if 50<i<100 else (f,r)))
    def test_low_speed(self):self.compare(self.seq(lambda i,t,f,r:(Sample(t,.35),Sample(t,.35))))
    def test_near_stop(self):self.compare(self.seq(lambda i,t,f,r:(Sample(t,.05),Sample(t,.05))))
    def test_single_return(self):
        b=self.compare(self.seq(lambda i,t,f,r:(f,None) if i>10 else (f,r)))
        self.assertFalse(b.diag[10])
    def test_skewed_return(self):
        b=self.compare(self.seq(lambda i,t,f,r:(Sample(t-.2,3),Sample(t,3)) if i>10 else (f,r)))
        self.assertFalse(b.diag[10])
    def test_reverse(self):self.compare(self.seq(lambda i,t,f,r:(Sample(t,-3),Sample(t,-3))))
    def test_zero_lock(self):self.compare(self.seq(lambda i,t,f,r:(Sample(t,0),Sample(t,0)) if i>5 else (f,r)))
    def test_true_stop(self):
        b=self.compare([(i*.05,Sample(i*.05,0),Sample(i*.05,0),Sample(i*.05,0)) for i in range(200)])
        self.assertEqual(b.last_estimate.mode,'STOPPED');self.assertEqual(b.s,0)
    def test_nonfinite(self):self.compare(self.seq(lambda i,t,f,r:(Sample(t,float('nan')),Sample(t,float('inf')))))
    def test_out_of_range_command(self):
        self.compare([(i*.05,Sample(i*.05,3),Sample(i*.05,3),Sample(i*.05,3)) for i in range(100)])
    def test_dwell_and_new_pairs(self):
        b=self.compare(self.seq(n=11));self.assertFalse(b.diag[10])
        b=self.compare(self.seq(n=15));self.assertTrue(b.diag[10])
    def test_bounded_memory(self):
        b=InstrumentedObserver(cfg,readout=readout);keys=set(vars(b))
        for args in self.seq(n=10000):
            b.step(*args);self.assertEqual(set(vars(b)),keys)
            self.assertEqual(len(b.diag),len(COLUMNS))
            self.assertTrue(b.diag_previous_pair is None or len(b.diag_previous_pair)==2)
    def test_reset(self):
        b=self.compare(self.seq());b.reset(velocity=2,position=9)
        self.assertEqual(b.s,9);self.assertIsNone(b.diag_trust_since);self.assertEqual(b.diag_pair_count,0)
    def test_snapshot_does_not_alias_lists(self):
        b=self.compare(self.seq(n=5));key=dynamical_state(b);used=key['used']
        b.step(.3,Sample(.3,0),Sample(.3,3),Sample(.3,3));self.assertEqual(key['used'],used);self.assertNotEqual(key['used'],tuple(b.used))
    def test_prefix_causal_future_values(self):
        def run(future):
            tl=Timeline(InstrumentedObserver(cfg,readout=readout),20,0);out=[]
            for ch,v in ((0,.1),(1,3),(2,3)):tl.ingest(ch,Sample(0,v))
            out.extend(e for e,_ in tl.advance(now=0));tl.ingest(1,Sample(2,future))
            for i in range(1,20):out.extend(e for e,_ in tl.advance(now=i*.05))
            return out
        self.assertEqual(run(3),run(20))
    def test_integral(self):
        b=InstrumentedObserver(cfg,readout=readout);old=None
        for args in self.seq(lambda i,t,f,r:(None,None) if 50<i<100 else (f,r)):
            e=b.step(*args)
            if old is not None:self.assertAlmostEqual(e.s-old.s,.5*(e.v+old.v)*(e.t-old.t),places=9)
            old=e

if __name__=='__main__':unittest.main()
