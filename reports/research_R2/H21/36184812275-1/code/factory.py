"""Build isolated baseline and patched H21 packages without editing active core."""
import dataclasses
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
BASE = '65bba39ed05c781f3f69a65c02f69931152cbfd9'
PKG = 'src/reserve_odometry/reserve_odometry'
CACHE = None


def canonical_bytes(path):
    return subprocess.check_output(['git','show',BASE+':'+path], cwd=ROOT)


def install_package(name, directory):
    spec=importlib.util.spec_from_file_location(name,directory/'__init__.py',submodule_search_locations=[str(directory)])
    module=importlib.util.module_from_spec(spec); sys.modules[name]=module; spec.loader.exec_module(module)
    return importlib.import_module(name+'.guarded_readout')


def factories():
    global CACHE
    if CACHE is not None:
        return CACHE
    tmp=tempfile.TemporaryDirectory(prefix='h21-runtime-')
    root=Path(tmp.name)
    for name in ('r2canonical','h21candidate'):
        d=root/name;d.mkdir()
        for f in ('__init__.py','core.py','guarded_readout.py'):
            path=PKG+'/'+f
            b=canonical_bytes(path)
            if (ROOT/path).read_bytes()!=b:
                raise AssertionError('Active runtime differs from fixed R2: '+path)
            (d/f).write_bytes(b)
    target=root/'h21candidate/core.py'
    text=target.read_text()
    before="        self.v = predicted\n        self.pv = p_prior\n"
    after="        accepted = self._supervise_updates(t, predicted, samples, statuses, accepted)\n"+before
    assert text.count(before)==1
    text=text.replace(before,after)
    marker='    def _output(self, t, a, mode, statuses, command_stale):\n'
    hook='    def _supervise_updates(self, t, predicted, samples, statuses, accepted):\n        return accepted\n\n'
    assert text.count(marker)==1
    target.write_text(text.replace(marker,hook+marker))
    (root/'h21candidate/reachable_interval.py').write_bytes((ROOT/PKG/'reachable_interval.py').read_bytes())
    base=install_package('r2canonical',root/'r2canonical')
    install_package('h21candidate',root/'h21candidate')
    candidate=importlib.import_module('h21candidate.reachable_interval')
    profile=json.loads((ROOT/'src/reserve_odometry/config/guarded_readout_v7.json').read_text())
    model=profile['config'];readout=profile['readout']
    assert readout==dict(gain=1.,holdoff_s=.5)
    assert model['adaptation_tau_s']==.5 and model['wheel_time_compensation']==0
    expected={}
    for line in (ROOT/'src/reserve_odometry/config/guarded_readout_v7.yaml').read_text().splitlines():
        k,sep,v=line.strip().partition(':')
        if k.startswith('model.') and sep:expected[k[6:]]=float(v)
    assert expected==model
    def make(kind):
        if kind=='baseline':return base.GuardedReadoutObserver(base.Config(**model),readout=base.ReadoutConfig(**readout))
        return candidate.ReachableIntervalObserver(base.Config(**model),readout=base.ReadoutConfig(**readout),enabled=kind!='off')
    CACHE=(make,candidate,tmp,root)
    return CACHE


def normalize(obj):
    # All project dataclasses contain only scalar fields; no copying needed.
    if dataclasses.is_dataclass(obj):return vars(obj)
    if isinstance(obj,dict):return {k:normalize(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)):return [normalize(x) for x in obj]
    return obj


def assert_off(base,off):
    for key,value in vars(base).items():
        if normalize(value)!=normalize(getattr(off,key)):
            raise AssertionError('Disabled baseline state differs: '+key)


def patch_text():
    import difflib
    _,_,_,d=factories()
    old=canonical_bytes(PKG+'/core.py').decode().splitlines(True)
    new=(d/'h21candidate/core.py').read_text().splitlines(True)
    return ''.join(difflib.unified_diff(old,new,fromfile='a/'+PKG+'/core.py',tofile='b/'+PKG+'/core.py'))


if __name__=='__main__':
    print(patch_text(),end='')
