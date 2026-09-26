"""Materialize an isolated H41 runtime; never rewrite canonical source files."""
from pathlib import Path
import difflib
import hashlib
import importlib
import importlib.util
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'src/reserve_odometry/reserve_odometry'
EXPECTED={'core.py':'a382e484f10208c6ea2fa0d9260b6876308724f8',
          'guarded_readout.py':'4b9033fd2a3ff88be3a7f82cb178d37041769e46'}
_KEEP=[]
_CLASS=None


def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('H41 hook source changed: '+old[:80])
    return text.replace(old,new,1)


def sources():
    raw={name:(BASE/name).read_bytes() for name in EXPECTED}
    for name,data in raw.items():
        blob=hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
        if blob!=EXPECTED[name]:raise ValueError('Pinned blob mismatch: '+name)
    core=raw['core.py'].decode()
    core=replace_once(core,'class Observer:\n','class Observer:\n    H41_HOOKS = True\n')
    old='        p_prior = self.pv + c.process_noise_v * dt * (4.0 if command_stale else 1.0)\n'
    core=replace_once(core,old,old+'''        if getattr(self, 'h41_enabled', False):
            p_prior = self._h41_predict(dt, u, previous_v, a_model, predicted, command_stale)
''')
    old='            self.pv = max(1e-8, (1 - gain) ** 2 * p_prior + gain * gain * r)\n'
    core=replace_once(core,old,old+'''            if getattr(self, 'h41_enabled', False):
                self._h41_correct(t, samples, accepted, agree, command_stale,
                                  p_prior, residual, r, gain)
''')
    read=raw['guarded_readout.py'].decode()
    old=read[read.index('                # These are the SAME'):read.index('                self._velocity_correction = (')]
    new="""                if getattr(self, 'h41_enabled', False):
                    # Actual pre-correction data: no scalar gain reconstruction.
                    p_prior = self.h41_prior
                    kalman_gain = self.h41_kv
                    acceleration = self.h41_a_model
                else:
"""+''.join('    '+line if line.strip() else line for line in old.splitlines(True))
    read=replace_once(read,old,new)
    return raw,{'core.py':core.encode(),'guarded_readout.py':read.encode(),
                'velocity_actuator.py':Path(__file__).with_name('velocity_actuator.py').read_bytes()}


def candidate_class():
    global _CLASS
    if _CLASS is None:
        _,files=sources()
        temp=tempfile.TemporaryDirectory(prefix='h41-runtime-');_KEEP.append(temp)
        root=Path(temp.name);(root/'__init__.py').write_text('')
        for name,data in files.items():(root/name).write_bytes(data)
        name='_h41_runtime'
        spec=importlib.util.spec_from_file_location(name,root/'__init__.py',submodule_search_locations=[str(root)])
        package=importlib.util.module_from_spec(spec);sys.modules[name]=package;spec.loader.exec_module(package)
        _CLASS=importlib.import_module(name+'.velocity_actuator').VelocityActuatorObserver
    return _CLASS


def patch_text():
    raw,files=sources();parts=[]
    for name,data in files.items():
        path='src/reserve_odometry/reserve_odometry/'+name
        parts.extend(difflib.unified_diff(raw.get(name,b'').decode().splitlines(True),data.decode().splitlines(True),
            fromfile='a/'+path if name in raw else '/dev/null',tofile='b/'+path))
    return ''.join(parts)

if __name__=='__main__':
    print(patch_text(),end='')
