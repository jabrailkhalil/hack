"""Pinned v8 source/profile helpers; never opens measurement data on import."""
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = 'e3b0c9c039d2953fbfcda51231263d38ef9f1024'
sys.path[:0] = [str(ROOT/'src/reserve_odometry'), str(ROOT/'tools/finalization')]
import evaluate as ev
from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.timeline import Timeline
np = ev.np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def profile():
    vals = {}
    for line in (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text().splitlines():
        key, sep, val = line.strip().partition(':')
        if sep and (key.startswith(('model.', 'readout.')) or key in
                    ('rate_hz', 'alignment_delay_s', 'front_scale', 'rear_scale')):
            vals[key] = float(val)
    c = Config(**{k[6:]:v for k,v in vals.items() if k.startswith('model.')})
    r = ReadoutConfig(**{k[8:]:v for k,v in vals.items() if k.startswith('readout.')})
    ops = {k:vals[k] for k in ('rate_hz','alignment_delay_s')}
    assert ops == {'rate_hz':20., 'alignment_delay_s':0.}
    assert asdict(r) == {'gain':1., 'holdoff_s':.5}
    assert c.adaptation_tau_s == .5 and c.wheel_time_compensation == 0.
    assert c.common_mode_quarantine_s == 1.5
    assert vals['front_scale'] == vals['rear_scale'] == 1/3.6
    launch = (ROOT/'src/reserve_odometry/launch/odometry.launch.py').read_text()
    assert "executable='guarded_odometry_node'" in launch and "'champion_v8.yaml'" in launch
    return c,r,ops


def integrity():
    pinned = json.loads((ROOT/'research/R3_H24/baseline_manifest.json').read_text())
    for p,digest in pinned.items():
        if sha(ROOT/p) != digest:
            raise ValueError('Pinned baseline/evaluator changed: '+p)
        if (ROOT/'.git').exists():
            raw = subprocess.check_output(['git','show',BASE+':'+p],cwd=ROOT)
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('Manifest is not the authorized baseline: '+p)
    profile()
    return pinned


def train_partition(store):
    groups = sorted({store.records[b]['group'] for b in store.plan['splits']['train']},
                    key=lambda g:hashlib.sha256(('R3-H24-fit-check:'+g).encode()).hexdigest())
    return {g:('check' if i%4==0 else 'fitting') for i,g in enumerate(groups)}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
