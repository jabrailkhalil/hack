"""Isolated H20 factories over fixed v7. Canonical runtime files are read-only.

The patch adds two soft-update hooks in a private copy of core. The inherited
hard gates, state dynamics, Timeline and guarded readout are unchanged.
"""
from dataclasses import asdict
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'src/reserve_odometry/reserve_odometry'
BASELINE = '65bba39ed05c781f3f69a65c02f69931152cbfd9'
OPS = {'rate_hz': 20.0, 'alignment_delay_s': 0.0}
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def profile():
    """Resolve the canonical YAML, not Config() or a historically named main."""
    values = {}
    for line in (SOURCE.parent / 'config/guarded_readout_v7.yaml').read_text().splitlines():
        key, sep, value = line.strip().partition(':')
        if sep and key.startswith(('model.', 'readout.')):
            values[key] = float(value)
    core = {k[6:]: v for k, v in values.items() if k.startswith('model.')}
    readout = {k[8:]: v for k, v in values.items() if k.startswith('readout.')}
    if readout != {'gain': 1.0, 'holdoff_s': 0.5} or core['wheel_time_compensation'] != 0 or core['adaptation_tau_s'] != .5:
        raise ValueError('Wrong R2 effective profile')
    return core, readout


def patched_core():
    source = (SOURCE / 'core.py').read_text()
    anchor = '        samples, statuses = [], []\n'
    hook = ("        h20_context = getattr(self, '_h20_context', None)\n"
            "        if h20_context is not None:\n"
            "            h20_context(t, u, target, a_model, predicted, previous_v, command_stale)\n")
    correction = '            gain = p_prior / (p_prior + r)\n'
    soft = ("            h20_weight = getattr(self, '_h20_weight', None)\n"
            "            if h20_weight is not None:\n"
            "                z, r = h20_weight(samples, accepted, agree, predicted, z, r)\n"
            "                residual = z - predicted\n")
    if source.count(anchor) != 1 or source.count(correction) != 1:
        raise ValueError('Core hooks no longer match fixed v7')
    return source.replace(anchor, hook + anchor).replace(correction, soft + correction)


def isolated(name, changed=False):
    if name in sys.modules:
        return sys.modules[name]
    package = types.ModuleType(name)
    package.__path__ = [str(SOURCE)]
    sys.modules[name] = package
    for part in ('core', 'guarded_readout'):
        path = SOURCE / (part + '.py')
        module = types.ModuleType(name + '.' + part)
        module.__file__ = str(path)
        module.__package__ = name
        sys.modules[module.__name__] = module
        code = patched_core() if changed and part == 'core' else path.read_text()
        exec(compile(code, str(path) + ('[H20]' if changed and part == 'core' else ''), 'exec'), module.__dict__)
        setattr(package, part, module)
    return package


BASE = isolated('_r2_h20_pristine')
CANDIDATE = isolated('_r2_h20_candidate', changed=True)


class AsymmetricObserver(CANDIDATE.guarded_readout.GuardedReadoutObserver):
    """Only directional soft weights; constant-size, vehicle-only state.

    Mode confirmation does not establish ground truth or identify common slip.
    Alpha=0 or an unconfirmed mode preserves original z/R arithmetic exactly.
    """
    def __init__(self, config=None, *, alpha=0.0, readout=None):
        if not math.isfinite(alpha) or not 0.0 <= alpha <= 0.5:
            raise ValueError('H20 alpha must be finite in [0, 0.5]')
        self._h20_alpha = float(alpha)
        super().__init__(config, readout=readout)

    def reset(self, **kwargs):
        super().reset(**kwargs)
        self._h20_mode = 0
        self._h20_direction = 0
        self._h20_since = None
        self._h20_confirmed = 0
        # Last update only, never an accumulating history; read only offline.
        self._h20_diag = None

    def _h20_context(self, t, u, target, a_model, predicted, old_v, stale):
        self._h20_diag = None
        if self._h20_alpha == 0.0:
            return
        direction = 1 if predicted > 0.0 else -1
        mode = 0
        if (self.initialized and not stale and abs(predicted) >= 0.5
                and old_v * predicted > 0.0):
            longitudinal = (direction * target, direction * self.drive_a,
                            direction * a_model)
            if u > self.c.command_deadband + .05 and min(longitudinal) > .05:
                mode = 1
            elif u < -(self.c.command_deadband + .05) and max(longitudinal) < -.05:
                mode = -1
        if mode == 0:
            self._h20_mode = self._h20_direction = self._h20_confirmed = 0
            self._h20_since = None
        else:
            if mode != self._h20_mode or direction != self._h20_direction:
                self._h20_since = t
            self._h20_mode, self._h20_direction = mode, direction
            self._h20_confirmed = mode if t - self._h20_since + 1e-9 >= .5 else 0

    def _h20_weight(self, samples, accepted, agree, predicted, z, r):
        if self._h20_alpha == 0.0:
            return z, r
        mode = self._h20_confirmed
        direction = 1 if predicted > 0.0 else -1
        b = 3.0 * self.c.wheel_sigma_mps
        innovations = tuple(direction * (samples[i].value - predicted) for i in accepted)
        weights = tuple(1.0 / (1.0 + self._h20_alpha * max(0.0, mode * e) ** 2 /
                        (b * b + max(0.0, mode * e) ** 2)) for e in innovations)
        original_z, original_r = z, r
        if mode and any(w != 1.0 for w in weights):
            total = sum(weights)
            z = sum(w * samples[i].value for w, i in zip(weights, accepted)) / total
            floor = self.c.wheel_sigma_mps ** 2 * (1.0 if len(accepted) == 2 and agree else 4.0)
            r = max(r, floor * max(1.0, abs(z - predicted) / b)) / (total / len(accepted))
        self._h20_diag = {
            'phase': mode, 'instantaneous_phase': self._h20_mode, 'direction': direction,
            'innovations': innovations, 'weights': weights,
            'changed': z != original_z or r != original_r,
            'predicted': predicted, 'z_original': original_z, 'z': z,
            'r_original': original_r, 'r': r,
        }
        return z, r


def baseline():
    c, r = profile()
    return BASE.guarded_readout.GuardedReadoutObserver(BASE.core.Config(**c),
                    readout=BASE.guarded_readout.ReadoutConfig(**r))


def candidate(alpha):
    c, r = profile()
    return AsymmetricObserver(CANDIDATE.core.Config(**c), alpha=alpha,
                    readout=CANDIDATE.guarded_readout.ReadoutConfig(**r))


def neutral(value):
    """Compare equal dataclass values from independent module namespaces."""
    if hasattr(value, '__dataclass_fields__'):
        return asdict(value)
    if isinstance(value, (list, tuple)):
        return [neutral(v) for v in value]
    if isinstance(value, dict):
        return {k: neutral(v) for k, v in value.items()}
    return value


def assert_disabled(base, off):
    for key, value in vars(base).items():
        if neutral(value) != neutral(getattr(off, key)):
            raise AssertionError('Disabled mismatch in original state: ' + key)
