"""H34 source/profile helpers. No measurement IO on import."""
from dataclasses import asdict, is_dataclass
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'research/R4_H34'
BASE='e3b0c9c039d2953fbfcda51231263d38ef9f1024'
sys.path[:0]=[str(ROOT/'src/reserve_odometry'),str(ROOT/'tools/finalization'),str(D)]
import evaluate as ev
from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.integration_h34 import DiscretizationObserver, mean_fraction
from pristine_package.guarded_readout import GuardedReadoutObserver as PristineObserver
np=ev.np
NAMES=['force_per_mass','power_per_mass','brake_per_mass','rolling_per_mass','quadratic_per_mass','command_exponent','actuator_tau_s']
LOW=np.array([.05,1.,.05,0.,0.,.3,.05]); HIGH=np.array([5.,100.,5.,.4,.005,3.,3.])


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')

def norm(v):
    if is_dataclass(v):return asdict(v)
    if isinstance(v,(list,tuple)):return [norm(x) for x in v]
    if isinstance(v,dict):return {k:norm(x) for k,x in v.items()}
    return v

def profile():
    vals={}
    for line in (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text().splitlines():
        k,s,v=line.strip().partition(':')
        if s and (k.startswith(('model.','readout.')) or k in ('rate_hz','alignment_delay_s')):vals[k]=float(v)
    c=Config(**{k[6:]:v for k,v in vals.items() if k.startswith('model.')})
    r=ReadoutConfig(**{k[8:]:v for k,v in vals.items() if k.startswith('readout.')})
    ops={k:vals[k] for k in ('rate_hz','alignment_delay_s')}
    assert ops==dict(rate_hz=20.,alignment_delay_s=0.) and asdict(r)==dict(gain=1.,holdoff_s=.5)
    assert c.common_mode_quarantine_s==1.5 and c.adaptation_tau_s==.5 and c.wheel_time_compensation==0.
    return c,r,ops

def theta0():
    c,_,_=profile()
    return np.array([c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m/c.mass_kg,
        c.max_power_w/c.mass_kg,c.max_brake_force_n/c.mass_kg,c.rolling_force_n/c.mass_kg,
        c.quadratic_drag_n_s2_m2/c.mass_kg,c.command_exponent,c.actuator_tau_s])

def configuration(theta):
    c,_,_=profile(); force,power,brake,roll,drag,gamma,tau=map(float,theta)
    c.total_motor_torque_nm=force*c.mass_kg*c.wheel_radius_m/(c.efficiency*c.gear_ratio)
    c.max_power_w=power*c.mass_kg;c.max_brake_force_n=brake*c.mass_kg
    c.rolling_force_n=roll*c.mass_kg;c.quadratic_drag_n_s2_m2=drag*c.mass_kg
    c.command_exponent=gamma;c.actuator_tau_s=tau;c.__post_init__();return c

def make(scheme,theta=None):
    c,r,_=profile();c=c if theta is None else configuration(theta)
    return PristineObserver(c,readout=r) if scheme=='baseline' else DiscretizationObserver(c,readout=r,scheme=scheme)

def integrity():
    receipt=json.loads((D/'SOURCE_RECEIPT.json').read_text());assert receipt['source_status']=='VERIFIED'
    modified={'src/reserve_odometry/reserve_odometry/core.py','src/reserve_odometry/reserve_odometry/guarded_readout.py'}
    for entry in receipt['files']:
        if entry['path'] not in modified:assert sha(ROOT/entry['path'])==entry['sha256'],entry['path']
    for entry in receipt['files']:
        p=entry['path']
        if p.startswith('src/reserve_odometry/reserve_odometry/'):
            q=D/'pristine_package'/p.split('/')[-1]; assert sha(q)==entry['sha256'],p
    return {'source_receipt_sha256':sha(D/'SOURCE_RECEIPT.json'),'unchanged_snapshot_files_checked':len(receipt['files'])-2,
            'baseline_tree':receipt['actual_git_tree'],'profile':asdict(profile()[0])}
