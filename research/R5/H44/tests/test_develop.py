import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import develop as d

class DevelopmentTests(unittest.TestCase):
    def events(self):
        rows=[]
        for t in np.arange(0,90,.1):
            for ch,v in [(0,.1),(1,1.5),(2,1.5)]:rows.append((t,ch,v))
        return np.array(rows)
    def test_low_speed_unchanged_anchor(self):
        events=self.events();windows=list(d.low_windows(events));self.assertEqual(len(windows),2)
        grid=d.ex.grid_channels(events);t,u,f,r,valid=grid
        expected=t[np.flatnonzero(valid&((f+r)/2>1)&((f+r)/2<2)&(u>=0)&(t>max(25,.1*t[-1]))&(t<t[-1]-25))[0]]
        self.assertEqual(windows[0][0]['start'],expected)
        self.assertEqual([f['end']-f['start'] for f,w in windows],[3,5])
    def test_recording_does_not_change_outputs(self):
        c,r,_=d.profile();fault=dict(start=30.,end=35.,kind='dropout')
        a,ai=d.g.predict(self.events(),(lambda c:d.GuardedReadoutObserver(c,readout=r),c),fault)
        b,bi=d.g.predict(self.events(),(lambda c:d.Recorder(c,r,fault),c),fault)
        np.testing.assert_array_equal(a,b);self.assertEqual(ai,bi)
    def test_unchanged_gate_rejects_zero_gain(self):
        c,r,_=d.profile();models={n:(lambda c:d.GuardedReadoutObserver(c,readout=r),c) for n in ('main','gnss','wheel')}
        ev=self.events();refs={'master':[(float(t),1.45) for t in np.arange(0,90,.1)],'rover':[]}
        row=dict(bag='fixture',group='one',**d.g.compare(ev,refs,models));fault=dict(kind='dropout',start=30.,end=35.)
        st=dict(bag='fixture',group='one',fault=fault,**d.g.compare(ev,refs,models,fault))
        gate=d.compare_gate([row],[st],[row],[st],[st],'gnss','main')
        self.assertEqual(gate['reasons'],['insufficient_gain'])
    def test_no_validation_loader(self):
        with self.assertRaises(PermissionError):d.DevelopmentStore('/nonexistent').load('30618_0259fe53','validation')

if __name__=='__main__':unittest.main()
