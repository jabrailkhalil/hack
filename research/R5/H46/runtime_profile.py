"""Explicit H46 profile selection. No fitting, bag-name inference or sensor reads.

This research-only factory is not installed or enabled by the canonical launch.
No fitted H46 artifact is supplied in the dependency-pending checkpoint.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Mapping

from reserve_odometry.core import Config
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig

ROOT = Path(__file__).resolve().parents[3]
BASELINE_SHA = 'b2783206000091ab11a1c11ac3ff79082188a4fb'
PROFILE_SHA = 'a6319d8e75615ee63b05bedccd1f79a27287666f084c8f14dd33ad993e7f067e'
PROFILE = ROOT / 'src/reserve_odometry/config/champion_v8.yaml'
LABELS = ('30618', '30639')


def baseline_configuration() -> tuple[Config, ReadoutConfig, dict]:
    """Read the complete pinned plain-scalar YAML, never Config defaults as a profile."""
    data = PROFILE.read_bytes()
    if hashlib.sha256(data).hexdigest() != PROFILE_SHA:
        raise ValueError('Canonical profile differs from the R5 pin')
    values = {}
    for line in data.decode().splitlines():
        key, sep, value = line.strip().partition(':')
        if sep and value.strip() and not key.startswith('#'):
            text = value.strip()
            values[key] = text if key == 'clock_mode' else float(text)
    model = {k[6:]: v for k, v in values.items() if k.startswith('model.')}
    if set(model) != set(Config.__dataclass_fields__):
        raise ValueError('Model field set differs; implicit defaults forbidden')
    readout = {k[8:]: v for k, v in values.items() if k.startswith('readout.')}
    if set(readout) != set(ReadoutConfig.__dataclass_fields__):
        raise ValueError('Readout field set differs')
    return Config(**model), ReadoutConfig(**readout), values


@dataclass(frozen=True)
class ForceParameters:
    force_per_mass: float
    power_per_mass: float
    brake_per_mass: float

    def __post_init__(self):
        for key, lo, hi in (('force_per_mass', .05, 5.),
                            ('power_per_mass', 1., 100.),
                            ('brake_per_mass', .05, 5.)):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f'{key} must be a real number')
            if not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError(f'{key} must be finite in [{lo}, {hi}]')

    @classmethod
    def from_config(cls, config: Config) -> ForceParameters:
        return cls(config.efficiency * config.gear_ratio * config.total_motor_torque_nm /
                   (config.wheel_radius_m * config.mass_kg),
                   config.max_power_w / config.mass_kg,
                   config.max_brake_force_n / config.mass_kg)

    def apply(self, base: Config) -> Config:
        # Baseline identity avoids a convert/back roundoff when explicitly equal.
        if self == self.from_config(base):
            return replace(base)
        return replace(base,
            total_motor_torque_nm=self.force_per_mass * base.mass_kg * base.wheel_radius_m /
                                  (base.efficiency * base.gear_ratio),
            max_power_w=self.power_per_mass * base.mass_kg,
            max_brake_force_n=self.brake_per_mass * base.mass_kg)


def _parameters(value: object) -> ForceParameters:
    if not isinstance(value, dict) or set(value) != set(ForceParameters.__dataclass_fields__):
        raise ValueError('Exactly three F/P/B values are required; no per-bag parameters')
    return ForceParameters(**value)


def validate_artifact(data: Mapping) -> dict[str, ForceParameters]:
    """Validate a future frozen export, not a teacher or dependency authorization.

    A schema check cannot establish that training actually happened. Its hashes
    must be independently bound to verified training evidence by the producer.
    """
    keys = {'schema_version', 'hypothesis_id', 'baseline_sha', 'baseline_profile_sha256',
            'status', 'mapping_status', 'dependencies_lock_sha256', 'training_manifest_sha256',
            'global_parameters', 'vehicle_parameters'}
    if not isinstance(data, dict) or set(data) != keys:
        raise ValueError('Unexpected or missing model artifact fields')
    required = {'schema_version': 'R5_H46_PARAMETERS_V1', 'hypothesis_id': 'R5-H46',
                'baseline_sha': BASELINE_SHA, 'baseline_profile_sha256': PROFILE_SHA,
                'status': 'TRAIN_FIT_COMPLETE', 'mapping_status': 'CONDITIONAL_ON_CONFIG'}
    if any(data.get(k) != v for k, v in required.items()):
        raise ValueError('Incomplete, wrong-baseline or unqualified artifact')
    for key in ('dependencies_lock_sha256', 'training_manifest_sha256'):
        if not isinstance(data.get(key), str) or not re.fullmatch('[0-9a-f]{64}', data[key]):
            raise ValueError('Missing provenance hash: ' + key)
    vehicles = data['vehicle_parameters']
    if not isinstance(vehicles, dict) or set(vehicles) != set(LABELS):
        raise ValueError('Exactly the two registered metadata labels are required')
    params = {label: _parameters(vehicles[label]) for label in LABELS}
    params['global'] = _parameters(data['global_parameters'])
    return params


def make_observer(*, vehicle_profile: str | None = None, enabled: bool = False,
                  artifact: Mapping | None = None) -> tuple[GuardedReadoutObserver, dict]:
    """Select once at initialization from explicit configuration only.

    Unknown and disabled selection is an exact baseline path even when artifact
    is missing/corrupt. A known enabled selection requires a complete export.
    Profile/global metadata never enters step(t,command,front,rear).
    """
    if not isinstance(enabled, bool):
        raise TypeError('enabled must be bool')
    config, readout, _ = baseline_configuration()
    known = isinstance(vehicle_profile, str) and vehicle_profile in LABELS + ('global',)
    if not enabled or not known:
        selection = {'selected': 'canonical_v8', 'active': False,
                     'reason': 'disabled' if not enabled else 'unknown_profile'}
    else:
        params = validate_artifact(artifact)
        config = params[vehicle_profile].apply(config)
        selection = {'selected': vehicle_profile, 'active': True,
                     'mapping_status': 'CONDITIONAL_ON_CONFIG'}
    return GuardedReadoutObserver(config, readout=readout), selection
