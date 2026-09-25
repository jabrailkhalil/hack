"""Load exact pinned v8 and isolated candidate without overwriting runtime files."""
from functools import lru_cache
from pathlib import Path
import hashlib
import sys
import types
from mechanism import NeutralGuard, patch_core

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src/reserve_odometry'))
from reserve_odometry.guarded_readout import GuardedReadoutObserver


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=2)
def candidate(enabled=True):
    core_path = ROOT/'src/reserve_odometry/reserve_odometry/core.py'
    guarded_path = ROOT/'src/reserve_odometry/reserve_odometry/guarded_readout.py'
    tag = 'enabled' if enabled else 'disabled'
    core_name = 'reserve_odometry._h13_core_'+tag
    module = types.ModuleType(core_name)
    module.__file__ = str(core_path)+'#isolated-H13'
    module.__package__ = 'reserve_odometry'
    module.NeutralGuard = NeutralGuard
    module.H13_ENABLED = enabled
    sys.modules[core_name] = module
    exec(compile(patch_core(core_path.read_text()), module.__file__, 'exec'), module.__dict__)
    guard_name = 'reserve_odometry._h13_readout_'+tag
    guarded = types.ModuleType(guard_name)
    guarded.__file__ = str(guarded_path)+'#isolated-H13'
    guarded.__package__ = 'reserve_odometry'
    sys.modules[guard_name] = guarded
    source = guarded_path.read_text().replace('from .core import ', f'from ._h13_core_{tag} import ')
    exec(compile(source, guarded.__file__, 'exec'), guarded.__dict__)
    return guarded.GuardedReadoutObserver
