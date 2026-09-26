"""One static traction-only candidate; no observer changes or runtime switching."""
from dataclasses import asdict
from functools import partial
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src/reserve_odometry'))
from reserve_odometry.core import Config
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig

HERE = Path(__file__).resolve().parent
PROFILE = ROOT / 'src/reserve_odometry/config/champion_v8.json'
# Exact H44 G artifact, not rounded effective F/m or P/m values.
TRACTION = {'total_motor_torque_nm': 3149.748421403977,
            'max_power_w': 429127.7144908343}
H44_BRAKE = 32884.7802577776
NAMES = ('main', 'candidate', 'h44_full_control', 'brake_only_control', 'off')


def verify_pins():
    """Fail closed before experiments if numerical source/measurement code moved."""
    pins = json.loads((HERE / 'BASELINE_PINS.json').read_text(encoding='utf-8'))
    for path, expected in pins.items():
        actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('Pinned source changed: ' + path)
    return pins


def configuration(name='candidate'):
    if name not in NAMES:
        raise ValueError('Unknown profile: ' + str(name))
    data = json.loads(PROFILE.read_text(encoding='utf-8'))
    values = dict(data['config'])
    if name in ('candidate', 'h44_full_control'):
        values.update(TRACTION)
    if name in ('h44_full_control', 'brake_only_control'):
        values['max_brake_force_n'] = H44_BRAKE
    # Fresh mutable Config on each call. Never transfer a live filter state.
    return Config(**values), ReadoutConfig(**data['readout'])


def make_observer(*, enabled=True):
    config, readout = configuration('candidate' if enabled else 'main')
    return GuardedReadoutObserver(config, readout=readout)


def models():
    """Adapter for the pinned guarded comparator; controls are not selectable."""
    verify_pins()
    result = {}
    for name in NAMES:
        config, readout = configuration(name)
        result[name] = (partial(GuardedReadoutObserver, readout=readout), config)
    return result


def model_manifest():
    result = {}
    for name in NAMES:
        config, readout = configuration(name)
        result[name] = {'config': asdict(config), 'readout': asdict(readout),
                        'selectable': name == 'candidate'}
    return result


def candidate_yaml():
    """Full ROS profile, including clocks/scales; exactly two parameter edits."""
    text = (ROOT / 'src/reserve_odometry/config/champion_v8.yaml').read_text(encoding='utf-8')
    baseline, _ = configuration('main')
    for key, value in TRACTION.items():
        old = f'    model.{key}: {getattr(baseline, key)}'
        if text.count(old) != 1:
            raise ValueError('Unexpected YAML field: ' + key)
        text = text.replace(old, f'    model.{key}: {value}')
    return '# EXPERIMENTAL: H44 traction only, v8 braking. NOT accuracy-validated.\n' + text


if __name__ == '__main__':
    verify_pins()
    print(json.dumps(model_manifest(), indent=2, allow_nan=False))
