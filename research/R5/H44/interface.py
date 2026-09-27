"""H44 parameter interface only: no fit, teacher reader, or candidate selection.

The original Config and GuardedReadoutObserver remain the numerical runtime.
Absolute theta is converted using a ratio to its baseline value so theta0
returns the original floating-point coefficient bytes exactly.
"""
from dataclasses import asdict, fields, replace
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src/reserve_odometry'))
from reserve_odometry.core import Config
from reserve_odometry.guarded_readout import ReadoutConfig

BASE = 'b2783206000091ab11a1c11ac3ff79082188a4fb'
TREE = '973d50d288e050325ee1c71a90fa8d81f2a099af'
PROFILE = 'src/reserve_odometry/config/champion_v8.yaml'
PARAMETERS = ('total_motor_torque_nm', 'max_power_w', 'max_brake_force_n')


def profile():
    """Read every model/readout parameter from the pinned flat YAML."""
    model, readout, operational = {}, {}, {}
    for line in (ROOT / PROFILE).read_text().splitlines():
        key, sep, value = line.strip().partition(':')
        if not sep:
            continue
        if key.startswith('model.'):
            model[key[6:]] = float(value)
        elif key.startswith('readout.'):
            readout[key[8:]] = float(value)
        elif key in ('rate_hz', 'alignment_delay_s'):
            operational[key] = float(value)
    if set(model) != {f.name for f in fields(Config)}:
        raise ValueError('Profile is not a complete Config; defaults are forbidden')
    if set(readout) != {f.name for f in fields(ReadoutConfig)}:
        raise ValueError('Profile is not a complete ReadoutConfig')
    if operational != {'rate_hz': 20.0, 'alignment_delay_s': 0.0}:
        raise ValueError('Unexpected operational profile')
    config, output = Config(**model), ReadoutConfig(**readout)
    if asdict(config) != model or asdict(output) != readout:
        raise ValueError('Configuration round trip changed values')
    return config, output, operational


def effective(config: Config):
    """Return force/mass, power/mass, brake/mass in SI units."""
    return (config.total_motor_torque_nm * config.efficiency * config.gear_ratio /
            (config.mass_kg * config.wheel_radius_m),
            config.max_power_w / config.mass_kg,
            config.max_brake_force_n / config.mass_kg)


def with_effective(base: Config, theta):
    """Change exactly three existing fields; theta is NOT a fitted artifact."""
    if len(theta) != 3:
        raise ValueError('Exactly three effective parameters are required')
    values = tuple(float(x) for x in theta)
    if any(not math.isfinite(x) or x <= 0 for x in values):
        raise ValueError('Expected positive finite effective parameters')
    prior = effective(base)
    return replace(base, **{key: getattr(base, key) * (x / ref)
                            for key, x, ref in zip(PARAMETERS, values, prior)})


class DependencyPending(RuntimeError):
    pass


def training_entrypoint(*args, **kwargs):
    """Deliberately fail closed until real upstream payload verification exists.

    Receipts, expected hashes and synthetic fixtures must not activate fitting.
    There is no implemented training path in this preflight-only checkpoint.
    """
    raise DependencyPending('H44 fitting is not implemented/authorized: verify '
                            'the exact H42 teacher and H43 atlas payloads first')
