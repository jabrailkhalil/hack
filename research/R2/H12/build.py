"""Load a verified isolated readout patch; never mutate production source."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src/reserve_odometry'))
TARGET = 'src/reserve_odometry/reserve_odometry/guarded_readout.py'
BASELINE = '65bba39ed05c781f3f69a65c02f69931152cbfd9'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify():
    manifest = json.loads((HERE / 'BASELINE.json').read_text())
    assert manifest['baseline'] == BASELINE
    for path, expected in manifest['sha256'].items():
        if sha(ROOT / path) != expected:
            raise ValueError('Pinned baseline/evaluator changed: ' + path)
    return manifest


@lru_cache(maxsize=1)
def load():
    manifest = verify()
    with tempfile.TemporaryDirectory(prefix='H12-isolated-') as tmp:
        p = Path(tmp) / TARGET
        p.parent.mkdir(parents=True)
        p.write_bytes((ROOT / TARGET).read_bytes())
        for extra in (['--check'], []):
            subprocess.run(['git', 'apply', *extra, str(HERE/'algorithm.patch')],
                           cwd=tmp, check=True, capture_output=True)
        raw = p.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest['candidate_sha256']:
        raise ValueError('Candidate hash mismatch')
    name = 'reserve_odometry._h12_integral_readout'
    mod = types.ModuleType(name)
    mod.__file__ = '<H12 patched guarded_readout.py>'
    sys.modules[name] = mod
    exec(compile(raw, mod.__file__, 'exec'), mod.__dict__)
    mod.source = raw
    return mod


def config():
    from reserve_odometry.core import Config
    data = json.loads((ROOT/'src/reserve_odometry/config/guarded_readout_v7.json').read_text())
    actual, readout, operational = {}, {}, {}
    for line in (ROOT/'src/reserve_odometry/config/guarded_readout_v7.yaml').read_text().splitlines():
        k, sep, v = line.strip().partition(':')
        if not sep:
            continue
        if k.startswith('model.'):
            actual[k[6:]] = float(v)
        elif k.startswith('readout.'):
            readout[k[8:]] = float(v)
        elif k in ('rate_hz', 'alignment_delay_s'):
            operational[k] = float(v)
    assert actual == data['config']
    assert readout == data['readout'] == {'gain': 1., 'holdoff_s': .5}
    assert operational == {'rate_hz': 20., 'alignment_delay_s': 0.}
    assert actual['wheel_time_compensation'] == 0 and actual['adaptation_tau_s'] == .5
    launch = (ROOT/'src/reserve_odometry/launch/odometry.launch.py').read_text()
    assert "executable='guarded_odometry_node'" in launch and 'guarded_readout_v7.yaml' in launch
    return Config(**actual)


def observer(enabled=True):
    mod = load()
    return mod.GuardedReadoutObserver(config(), readout=mod.ReadoutConfig(integral_age=enabled))


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write', type=Path, required=True)
    a = p.parse_args()
    a.write.mkdir(parents=True, exist_ok=False)
    (a.write/'guarded_readout.py').write_bytes(load().source)
    (a.write/'candidate.json').write_text(json.dumps({'config':vars(config()),
        'readout':{'gain':1.,'holdoff_s':.5,'integral_age':True}}, indent=2)+'\n')
    print('Isolated candidate ready; checkout alone does not enable H12.')
