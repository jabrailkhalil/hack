"""H13 implementation checks; none constitute real-record accuracy evidence."""
import ast
from dataclasses import asdict, is_dataclass
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src/reserve_odometry'))
from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver
from reserve_odometry.interval_disturbance import ModelHistory
from reserve_odometry.interval_readout import IntervalReadoutObserver
BASE = '65bba39ed05c781f3f69a65c02f69931152cbfd9'
PROFILE = json.loads((ROOT/'src/reserve_odometry/config/guarded_readout_v7.json').read_text())

def original_source():
    path = os.environ.get('H13_BASELINE_CORE')
    return Path(path).read_text() if path else subprocess.check_output(
        ['git', 'show', BASE+':src/reserve_odometry/reserve_odometry/core.py'], cwd=ROOT, text=True)

def originals():
    package = types.ModuleType('h13_original'); package.__path__ = []
    sys.modules[package.__name__] = package
    core = types.ModuleType('h13_original.core'); sys.modules[core.__name__] = core
    exec(compile(original_source(), '<pinned v7 core>', 'exec'), core.__dict__)
    readout = types.ModuleType('h13_original.guarded_readout'); sys.modules[readout.__name__] = readout
    exec(compile((ROOT/'src/reserve_odometry/reserve_odometry/guarded_readout.py').read_text(),
                 '<pinned v7 readout>', 'exec'), readout.__dict__)
    return core, readout

OriginalCore, OriginalReadout = originals()

def make(enabled=1):
    return IntervalReadoutObserver(Config(**PROFILE['config']), enabled=bool(enabled))

def normalize(x):
    if is_dataclass(x): return asdict(x)
    if isinstance(x, list): return [normalize(v) for v in x]
    return x

def stream(n=2000):
    rng = random.Random(13)
    front = rear = None
    for k in range(n):
        t = k*.05
        v = 4+.35*math.sin(t*.8)
        if k%2 == 0:
            front=Sample(t-.015, v+rng.uniform(-.003,.003))
            rear=Sample(t-.013, v+rng.uniform(-.003,.003))
        if 200 <= k%500 < 260: front=rear=None
        if 400 <= k%500 < 420: front=rear=Sample(t,0.)
        yield t, Sample(t,.25 if k%120<60 else 0.), front, rear

class H13Tests(unittest.TestCase):
    def test_01_disabled_all_old_state_and_estimate_exact(self):
        a=make(0); b=OriginalReadout.GuardedReadoutObserver(OriginalCore.Config(**PROFILE['config']))
        for args in stream(6000):
            self.assertEqual(asdict(a.step(*args)),asdict(b.step(*args)))
            for key,value in vars(b).items():
                if key == 'c':
                    self.assertEqual({k:getattr(a.c,k) for k in asdict(b.c)},asdict(b.c))
                    self.assertFalse(a._interval_enabled)
                    continue
                self.assertEqual(normalize(getattr(a,key)),normalize(value),key)
        self.assertIsNone(a._interval_history)
    def test_02_constant(self):
        h=ModelHistory()
        for k in range(10): h.record(None if k==0 else (k-1)*.05,k*.05,2.)
        self.assertAlmostEqual(h.mean(.017,.217)[0],2.)
        self.assertAlmostEqual(h.target(.017,.217,2.3,.3,2.,0.),.3)
    def test_03_affine_fractional_exact(self):
        h=ModelHistory()
        for k in range(10): h.record(None if k==0 else (k-1)*.05,k*.05,1+3*k*.05)
        self.assertAlmostEqual(h.mean(.017,.217)[0],1+3*(.017+.217)/2)
    def test_04_wolfram_identity_numeric(self):
        t,h,delta,g0,j,d=.5,.03,.1,.4,1.2,.15
        gm=g0+j*(t-h-delta/2); measured=gm+d
        self.assertAlmostEqual(measured-(g0+j*t)-d,-j*(h+delta/2))
        self.assertAlmostEqual(measured-gm,d)
    def test_05_no_extrapolation(self):
        h=ModelHistory(); h.record(None,0.,1.); h.record(0.,.05,2.)
        self.assertIsNone(h.mean(-.01,.03)[0]); self.assertIsNone(h.mean(.01,.06)[0])
    def test_06_stale_segment_skips(self):
        h=ModelHistory(); h.record(None,0.,1.); h.record(0.,.05,2.,'stale')
        self.assertIsNone(h.target(.01,.04,1.,0.,2.,.2)); self.assertEqual(h.counts['stale'],1)
    def test_07_reset_clears(self):
        a=make()
        for args in stream(30): a.step(*args)
        a.reset(); self.assertEqual(len(a._interval_history.segments),0)
        self.assertEqual(a._interval_history.counts['eligible'],0)
    def test_08_gap_never_bridged(self):
        h=ModelHistory(); h.record(None,0.,1.); h.record(0.,.05,1.); h.record(.15,.20,1.)
        self.assertEqual(len(h.segments),0); self.assertIsNone(h.mean(.01,.19)[0])
        a=make(); a.step(0.,Sample(0,0),Sample(0,1),Sample(0,1))
        with self.assertRaises(ValueError): a.step(1.)
    def test_09_two_bounds(self):
        for dt in (.001,.05):
            h=ModelHistory()
            for k in range(20000):
                h.record(None if k==0 else (k-1)*dt,k*dt,1.)
                self.assertLessEqual(len(h.segments),32)
                if h.segments: self.assertLessEqual(k*dt-h.segments[0].start,.75+1e-9)
    def test_10_prefix(self):
        a=make(); b=make(); data=list(stream(500))
        prefix=[asdict(a.step(*x)) for x in data[:300]]
        full=[asdict(b.step(*x)) for x in data]
        self.assertEqual(prefix,full[:300])
    def test_11_duplicates_do_not_train(self):
        a=make(); a.reset(velocity=4.)
        for k in range(5): a.step(k*.05,Sample(k*.05,.2),Sample(0,4.),Sample(0,4.))
        self.assertEqual(a._interval_history.counts['eligible'],0)
    def test_12_future_rejected(self):
        a=make(); a.reset(velocity=4.)
        e=a.step(0.,Sample(1,.2),Sample(1,4),Sample(1,4))
        self.assertEqual(e.mode,'MODEL_ONLY'); self.assertTrue(e.command_stale)
        self.assertEqual(a._interval_history.counts['eligible'],0)
    def test_13_state_bounded_finite(self):
        a=make()
        for args in stream(15000):
            e=a.step(*args)
            self.assertTrue(all(math.isfinite(getattr(e,k)) for k in ('v','s','disturbance','variance_v','variance_s')))
            self.assertLessEqual(abs(e.disturbance),a.c.disturbance_limit_mps2)
            self.assertLessEqual(abs(e.v),a.c.max_speed_mps)
            self.assertLessEqual(len(a._interval_history.segments),32)
        self.assertGreater(a._interval_history.counts['applied'],100)
    def test_14_zero_lock_and_true_stop(self):
        a=make(); a.reset(velocity=1.5)
        for k in range(40):
            t=k*.05; e=a.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
            self.assertNotEqual(e.mode,'STOPPED')
        b=make()
        for k in range(40):
            t=k*.05; e=b.step(t,Sample(t,0),Sample(t,0),Sample(t,0))
        self.assertEqual(e.mode,'STOPPED'); self.assertEqual(e.v,0.)
    def test_15_clipping_invalidates(self):
        a=make(); a.reset(velocity=39.99); a.drive_a=10
        a.step(0,Sample(0,1),Sample(0,39.99),Sample(0,39.99))
        a.step(.05,Sample(.05,1),Sample(.05,40),Sample(.05,40))
        self.assertEqual(a._interval_history.previous[2],'clipped')
    def test_16_original_guards_unchanged(self):
        def funcs(source):
            tree=ast.parse(source)
            observer=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Observer')
            return {f.name:ast.dump(f,include_attributes=False) for f in observer.body if isinstance(f,ast.FunctionDef)}
        a=funcs(original_source()); b=funcs((ROOT/'src/reserve_odometry/reserve_odometry/core.py').read_text())
        for key in ('drive_target','resistance','_valid','_wheel','_clear_reacquire','_take_pending_pair','_reacquire_pair','_output'):
            self.assertEqual(a[key],b[key],key)
    def test_17_skip_control_only_target(self):
        a=ModelHistory(); a.endpoint_control=True
        for k in range(5): a.record(None if k==0 else (k-1)*.05,k*.05,1+k*.05)
        self.assertEqual(a.target(.01,.17,2.,9.,1.2,0.),9.)
        self.assertIsNone(a.target(-1.,.17,2.,9.,1.2,0.))
    def test_18_nonfinite_and_config(self):
        for x in (-1,.5,2,float('nan')):
            with self.assertRaises(ValueError): IntervalReadoutObserver(enabled=x)
        h=ModelHistory(); h.record(None,0.,float('nan')); self.assertIsNone(h.previous)
        a=make()
        with self.assertRaises(ValueError): a.step(float('nan'))

if __name__=='__main__': unittest.main(verbosity=2)
