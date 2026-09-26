"""Explicit H35 factory: canonical v8 baseline; byte-pinned private patched copy.

No evaluator code/metric or canonical source is modified. Generated files make
module.__file__ and exact measured runtime bytes inspectable. Do not apply the
standalone core hook patch on top of this factory; it already applies it.
"""
import difflib, importlib.util, json, sys
from pathlib import Path
from common import ROOT,HERE,Config,GuardedReadoutObserver,ReadoutConfig,profile,sha,load_module

CORE_SHA='candidates-pinned-by-receipt'
PRIVATE=HERE/'.generated'
OLD='        alpha = 1.0 - math.exp(-dt / c.actuator_tau_s)\n        self.drive_a += alpha * (target - self.drive_a)\n'
NEW='        self.drive_a = self._advance_drive(target, dt, command_stale)\n'
METHOD='    def _advance_drive(self, target, dt, command_stale):\n        alpha = 1.0 - math.exp(-dt / self.c.actuator_tau_s)\n        return self.drive_a + alpha * (target - self.drive_a)\n\n'

def prepare():
    source=ROOT/'src/reserve_odometry/reserve_odometry'
    core=(source/'core.py').read_text()
    if core.count(OLD)!=1 or core.count('    def drive_target(')!=1:
        raise ValueError('Unexpected core; require exact pristine v8')
    patched=core.replace(OLD,NEW).replace('    def drive_target(',METHOD+'    def drive_target(')
    PRIVATE.mkdir(exist_ok=True)
    payloads={'__init__.py':'', 'core.py':patched,
              'guarded_readout.py':(source/'guarded_readout.py').read_text(),
              'release_observer.py':(HERE/'release_observer.py').read_text()}
    for path,text in payloads.items():
        p=PRIVATE/path
        if p.exists() and p.read_text()!=text:
            raise ValueError('Generated runtime differs: use a new isolated directory')
        if not p.exists():p.write_text(text)
    spec=importlib.util.spec_from_file_location('_h35_runtime',PRIVATE/'__init__.py',submodule_search_locations=[str(PRIVATE)])
    pkg=importlib.util.module_from_spec(spec);sys.modules['_h35_runtime']=pkg;spec.loader.exec_module(pkg)
    module=load_module('_h35_runtime.release_observer',PRIVATE/'release_observer.py')
    return module

runtime=prepare()
ReleaseObserver=runtime.ReleaseObserver

def build(ratio=None):
    cfg,ro=profile()
    return GuardedReadoutObserver(cfg,readout=ro) if ratio is None else ReleaseObserver(cfg,readout=ro,release_ratio=ratio)

def enabled_identity():
    o=build(.5)
    return dict(class_name=type(o).__name__,module_file=sys.modules[type(o).__module__].__file__,
                canonical_module_file=sys.modules[GuardedReadoutObserver.__module__].__file__,
                generated_sha256={str(p.relative_to(ROOT)):sha(p) for p in PRIVATE.glob('*.py')},
                config=vars(o.c),readout=vars(o.readout),ratios=[.5,2.])

if __name__=='__main__':
    print(json.dumps(enabled_identity(),indent=2))
