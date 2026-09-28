"""Explicit factory: load every parameter of the exact canonical v8 profile.

This research module is not an installed ROS entry point. No calibrated artifact
exists until H42/H43 verification and the preregistered data stages complete.
"""
from dataclasses import fields
import hashlib
from pathlib import Path

from reserve_odometry.core import Config
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from runtime import ResidualScale, ResidualScaleObserver

ROOT = Path(__file__).resolve().parents[3]
PROFILE = ROOT / 'src/reserve_odometry/config/champion_v8.yaml'
PROFILE_SHA256 = 'a6319d8e75615ee63b05bedccd1f79a27287666f084c8f14dd33ad993e7f067e'


def load_profile():
    raw = PROFILE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROFILE_SHA256:
        raise ValueError('Canonical profile bytes differ from the pinned baseline')
    model, readout, ops = {}, {}, {}
    for line in raw.decode('utf-8').splitlines():
        key, sep, value = line.strip().partition(':')
        if not sep or key.startswith('#'):
            continue
        if key.startswith('model.'):
            model[key[6:]] = float(value)
        elif key.startswith('readout.'):
            readout[key[8:]] = float(value)
        elif key in ('rate_hz', 'alignment_delay_s', 'front_scale', 'rear_scale'):
            ops[key] = float(value)
    if set(model) != {f.name for f in fields(Config)}:
        raise ValueError('Profile must explicitly define all current Config fields')
    if set(readout) != {f.name for f in fields(ReadoutConfig)}:
        raise ValueError('Readout parameters are incomplete')
    if ops != dict(rate_hz=20.0, alignment_delay_s=0.0,
                   front_scale=1/3.6, rear_scale=1/3.6):
        raise ValueError('Unit conversion or output schedule changed')
    return Config(**model), ReadoutConfig(**readout), ops


def baseline():
    config, readout, _ = load_profile()
    return GuardedReadoutObserver(config, readout=readout)


def prototype(calibration: ResidualScale):
    config, readout, _ = load_profile()
    return ResidualScaleObserver(config, calibration=calibration, readout=readout)
