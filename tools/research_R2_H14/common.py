"""Fixed R2 baseline loading and new source manifest, not old-pin rewriting."""
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
BASE = '65bba39ed05c781f3f69a65c02f69931152cbfd9'
sys.path[:0] = [str(ROOT/'src/reserve_odometry'), str(ROOT/'tools/finalization')]
import evaluate as ev
from reserve_odometry.core import Config
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.async_adaptation import AsyncAdaptationObserver


def git_bytes(path):
    return subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT)


def load_pristine():
    package = types.ModuleType('_h14_pristine'); package.__path__ = []
    sys.modules[package.__name__] = package
    for short in ('core', 'guarded_readout'):
        name = package.__name__+'.'+short
        mod = types.ModuleType(name); mod.__package__ = package.__name__
        sys.modules[name] = mod
        code = git_bytes('src/reserve_odometry/reserve_odometry/'+short+'.py')
        exec(compile(code,BASE+'/'+short+'.py','exec'),mod.__dict__)
    return sys.modules['_h14_pristine.guarded_readout'].GuardedReadoutObserver


Pristine = load_pristine()


def profile():
    p = ROOT/'src/reserve_odometry/config/guarded_readout_v7.yaml'
    values = {}
    for line in p.read_text().splitlines():
        k,sep,v = line.strip().partition(':')
        if sep and (k.startswith('model.') or k.startswith('readout.') or
                    k in ('rate_hz','alignment_delay_s','front_scale','rear_scale')):
            values[k] = float(v)
    c = Config(**{k[6:]:v for k,v in values.items() if k.startswith('model.')})
    rc = ReadoutConfig(**{k[8:]:v for k,v in values.items() if k.startswith('readout.')})
    ops = {k:values[k] for k in ('rate_hz','alignment_delay_s')}
    assert ops == dict(rate_hz=20., alignment_delay_s=0.)
    assert asdict(rc) == dict(gain=1., holdoff_s=.5)
    assert c.wheel_time_compensation == 0. and c.adaptation_tau_s == .5
    assert values['front_scale'] == values['rear_scale'] == 1/3.6
    launch=(ROOT/'src/reserve_odometry/launch/odometry.launch.py').read_text()
    assert "executable='guarded_odometry_node'" in launch
    assert "'guarded_readout_v7.yaml'" in launch
    return c,rc,ops


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def manifest():
    pinned = ['tools/finalization/evaluate.py','tools/research_v3/experiment.py',
              'tools/research_v3/manifest.py','tools/export_bags.py',
              'tools/research_v6/compare.py','tools/research_guarded/compare.py',
              'research/split_v3.json','research/plan_v3.json',
              'src/reserve_odometry/reserve_odometry/guarded_readout.py',
              'src/reserve_odometry/reserve_odometry/timeline.py',
              'src/reserve_odometry/config/guarded_readout_v7.yaml',
              'src/reserve_odometry/launch/odometry.launch.py']
    for p in pinned:
        if (ROOT/p).read_bytes()!=git_bytes(p):
            raise ValueError('immutable baseline/evaluator modified: '+p)
    # Verify applied core is EXACTLY baseline + the reviewed research patch.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp); p='src/reserve_odometry/reserve_odometry/core.py'
        (tmp/p).parent.mkdir(parents=True); (tmp/p).write_bytes(git_bytes(p))
        subprocess.run(['git','apply',str(ROOT/'research/R2_H14/adaptation-hook.patch')],
                       cwd=tmp,check=True)
        assert (tmp/p).read_bytes()==(ROOT/p).read_bytes()
    paths=pinned+['src/reserve_odometry/reserve_odometry/core.py',
                  'src/reserve_odometry/reserve_odometry/async_adaptation.py',
                  'research/R2_H14/adaptation-hook.patch']
    paths+= [str(p.relative_to(ROOT)) for p in sorted((ROOT/'tools/research_R2_H14').glob('*.py'))]
    paths += [str(p.relative_to(ROOT)) for p in sorted((ROOT/'research/R2_H14/tests').glob('*.py'))]
    if (ROOT/'research/R2_H14/PLAN.md').exists():
        paths.append('research/R2_H14/PLAN.md')
    return {p:sha(ROOT/p) for p in paths}
