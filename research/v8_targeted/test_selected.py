from dataclasses import asdict
from pathlib import Path
import sys
import unittest
import yaml
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import selected
import candidates as c
from test_candidates import inputs

class SelectedTests(unittest.TestCase):
    def test_manifest_pins(self):self.assertFalse(selected.verify()['default_changed'])
    def test_exact_float(self):
        self.assertEqual(selected.make_observer().c.disturbance_limit_mps2,0.7000000000000001)
    def test_yaml_full_parity(self):
        p=yaml.safe_load((HERE/'v8_residual070.yaml').read_text())['reserve_odometry']['ros__parameters']
        o=selected.make_observer()
        self.assertEqual({k[6:]:v for k,v in p.items() if k.startswith('model.')},asdict(o.c))
        self.assertEqual({k[8:]:v for k,v in p.items() if k.startswith('readout.')},asdict(o.readout))
        self.assertEqual(p['rate_hz'],20.);self.assertEqual(p['alignment_delay_s'],0.)
    def test_only_one_changed_field(self):
        a,b=selected.make_observer(),selected.make_observer(enabled=False)
        self.assertEqual([k for k in asdict(a.c) if getattr(a.c,k)!=getattr(b.c,k)],['disturbance_limit_mps2'])
    def test_off_entire_state_parity(self):
        a=selected.make_observer(enabled=False);cfg,ro=c.configuration('main');b=c.GuardedReadoutObserver(cfg,readout=ro)
        for args in inputs(5000):
            self.assertEqual(a.step(*args),b.step(*args));self.assertEqual(vars(a),vars(b))
    def test_selected_exact_measured_variant(self):
        a=selected.make_observer();cls,cfg=c.models(['disturbance_070'])['disturbance_070'];b=cls(cfg)
        for args in inputs(5000):
            self.assertEqual(a.step(*args),b.step(*args));self.assertEqual(vars(a),vars(b))

if __name__=='__main__':unittest.main()
