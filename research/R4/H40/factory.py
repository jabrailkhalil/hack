"""One opt-in Coulomb predictor in a private copy; canonical files untouched."""
import difflib
import hashlib
import importlib.util
import math
from pathlib import Path
import sys
import tempfile
import types

ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'src/reserve_odometry/reserve_odometry'
CORE_PIN='67ee39edeb80f31876f5c45cb3efec26eb73844a106f7b4c876a944b6f7cc5dc'
READOUT_PIN='6303c1230ff800e370875f7238912e47a0564da1b21d42ccf8f417f75b2e05e0'

def clamp(x,lo,hi):return max(lo,min(hi,x))

def prediction(c,v,dt,drive,disturbance):
    """Implicit Coulomb / explicit quadratic drag; acceleration before sign guard.

    Branching on free velocity avoids (prox-v)/dt cancellation for tiny dt.
    Energy assertion applies only to the zero-force, zero-drag toy case.
    """
    if dt<0 or not all(math.isfinite(x) for x in (v,dt,drive,disturbance)):
        raise ValueError('Invalid predictor input')
    if dt==0:return 0.,v
    r0=c.rolling_force_n/c.mass_kg
    net=drive+disturbance-c.quadratic_drag_n_s2_m2*v*abs(v)/c.mass_kg
    free=v+dt*net;limit=dt*r0
    stuck=abs(free)<=limit
    a=(-v/dt if stuck else net-math.copysign(r0,free))
    a=clamp(a,-c.max_accel_mps2,c.max_accel_mps2)
    predicted=clamp(v+dt*a,-c.max_speed_mps,c.max_speed_mps)
    if stuck and abs(v)<=dt*c.max_accel_mps2:predicted=0.
    return a,predicted

def sources():
    core=(SOURCE/'core.py').read_text();readout=(SOURCE/'guarded_readout.py').read_text()
    if hashlib.sha256(core.encode()).hexdigest()!=CORE_PIN or hashlib.sha256(readout.encode()).hexdigest()!=READOUT_PIN:
        raise ValueError('Not the pinned full v8 source')
    old='''        a_model = clip(self.drive_a - self.resistance(self.v) + self.disturbance,
                       -c.max_accel_mps2, c.max_accel_mps2)
        predicted = clip(self.v + dt * a_model, -c.max_speed_mps, c.max_speed_mps)
'''
    new='''        if getattr(self, '_h40_enabled', False):
            a_model, predicted = self._h40_prediction(self.v, dt, self.drive_a, self.disturbance)
        else:
'''+''.join('    '+line+'\n' for line in old.splitlines())
    assert core.count(old)==1;changed=core.replace(old,new)
    old_r='''                acceleration = clip(self.drive_a - self.resistance(old_v) + old_disturbance,
                                    -self.c.max_accel_mps2, self.c.max_accel_mps2)
'''
    new_r='''                if getattr(self, '_h40_enabled', False):
                    acceleration = self._h40_prediction(old_v, dt, self.drive_a, old_disturbance)[0]
                else:
'''+''.join('    '+line+'\n' for line in old_r.splitlines())
    assert readout.count(old_r)==1
    return {'core.py':changed,'guarded_readout.py':readout.replace(old_r,new_r)}

# Real generated files provide truthful module.__file__ paths for replay manifests.
TEMP=Path(tempfile.mkdtemp(prefix='r4-h40-runtime-'))
PKG='_r4_h40_runtime'
package=types.ModuleType(PKG);package.__path__=[str(TEMP)];sys.modules[PKG]=package
for part,code in sources().items():
    file=TEMP/part;file.write_text(code)
    name=PKG+'.'+file.stem
    spec=importlib.util.spec_from_file_location(name,file);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);setattr(package,file.stem,m)

class CoulombObserver(package.guarded_readout.GuardedReadoutObserver):
    def __init__(self,config=None,*,readout=None,enabled=True):
        if not isinstance(enabled,bool):raise ValueError('enabled must be bool')
        self._h40_enabled=enabled
        super().__init__(config,readout=readout)
    def _h40_prediction(self,v,dt,drive,disturbance):
        return prediction(self.c,v,dt,drive,disturbance)

def candidate(enabled=True):
    # Scientific dependencies are used only by the offline profile factory.
    from common import profile
    c,r=profile()
    from dataclasses import asdict
    return CoulombObserver(package.core.Config(**asdict(c)),
        readout=package.guarded_readout.ReadoutConfig(**asdict(r)),enabled=enabled)

def patch():
    result=''
    for name,code in sources().items():
        path='src/reserve_odometry/reserve_odometry/'+name
        result+=''.join(difflib.unified_diff((SOURCE/name).read_text().splitlines(True),code.splitlines(True),fromfile='a/'+path,tofile='b/'+path))
    return result
if __name__=='__main__':print(patch(),end='')
