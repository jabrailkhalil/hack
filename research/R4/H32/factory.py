"""Load one isolated three-line hook from the verified complete v8 source.

Original classes and files are never modified. Compiled step reuses canonical
Sample/Estimate classes; guarded_readout inherits the hooked method through MRO.
"""
from pathlib import Path
import hashlib
import inspect
import textwrap
import difflib
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src/reserve_odometry'))
from reserve_odometry import core
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from event_time import CommandEventMixin, CommandEventTimeline
CORE_SHA = '67ee39edeb80f31876f5c45cb3efec26eb73844a106f7b4c876a944b6f7cc5dc'
RAW = Path(core.__file__).read_bytes()
if hashlib.sha256(RAW).hexdigest() != CORE_SHA:
    raise ValueError('H32 requires the exact pinned v8 core')
OLD = '''        target = self.drive_target(u, self.v)
        alpha = 1.0 - math.exp(-dt / c.actuator_tau_s)
        self.drive_a += alpha * (target - self.drive_a)'''
NEW = '        self._h32_propagate_drive(dt, u, t, command)'
if RAW.decode().count(OLD) != 1:
    raise ValueError('Drive hook is not unique')
PATCHED_CORE = RAW.decode().replace(OLD, NEW)
HOOK_PATCH = ''.join(difflib.unified_diff(RAW.decode().splitlines(True),
    PATCHED_CORE.splitlines(True), fromfile='a/src/reserve_odometry/reserve_odometry/core.py',
    tofile='b/src/reserve_odometry/reserve_odometry/core.py'))
STEP_SOURCE = textwrap.dedent(inspect.getsource(core.Observer.step).replace(OLD, NEW))
namespace = dict(vars(core))
exec(compile(STEP_SOURCE, '<R4-H32 verified three-line drive hook>', 'exec'), namespace)

class HookedCore(core.Observer):
    step = namespace['step']

class CommandEventObserver(CommandEventMixin, GuardedReadoutObserver, HookedCore):
    pass

def candidate(config, enabled=True):
    return CommandEventObserver(config, readout=ReadoutConfig(gain=1., holdoff_s=.5), enabled=enabled)

if __name__ == '__main__':
    print(HOOK_PATCH, end='')
