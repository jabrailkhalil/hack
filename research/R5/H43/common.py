"""R5-H43: isolated role/factory adapter, not a replacement scorer."""
from __future__ import annotations
from dataclasses import asdict, fields
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = 'b2783206000091ab11a1c11ac3ff79082188a4fb'
TREE = '973d50d288e050325ee1c71a90fa8d81f2a099af'
H36 = '4bd4908821e55e08195f08bd88eb7cfab17dc3c7'
H36_BLOB = 'daf4877655dbf0716c0fb1e4f17d331c84becf64'
PLAN_COMMIT = '84d37559f91ed69a3d3a02de608ac411e2bdc143'
sys.path[:0] = [str(ROOT/'tools/finalization'), str(ROOT/'src/reserve_odometry')]
import evaluate as ev
import numpy as np
from reserve_odometry.core import Config, Sample, clip
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig


def module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


gc = module('h43_original_guarded', 'tools/research_guarded/compare.py')
v6 = module('h43_original_v6', 'tools/research_v6/compare.py')


def sha(path: Path) -> str:
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def profile(path: Path | None = None):
    path = path or ROOT/'src/reserve_odometry/config/champion_v8.yaml'
    p = {}
    for line in path.read_text().splitlines():
        key, sep, val = line.strip().partition(':')
        if sep and not key.startswith('#') and val.strip():
            try: p[key] = float(val)
            except ValueError: p[key] = val.strip()
    cfg = {key[6:]:value for key,value in p.items() if key.startswith('model.')}
    if set(cfg) != {f.name for f in fields(Config)}:
        raise ValueError('Incomplete/extraneous model profile')
    read = {key[8:]:value for key,value in p.items() if key.startswith('readout.')}
    assert read == {'gain':1., 'holdoff_s':.5}
    assert p['rate_hz'] == 20 and p['alignment_delay_s'] == 0
    assert cfg['adaptation_tau_s'] == .5 and cfg['common_mode_quarantine_s'] == 1.5
    assert cfg['wheel_time_compensation'] == 0
    return Config(**cfg), ReadoutConfig(**read)


def integrity():
    pins = json.loads((HERE/'NUMERICAL_PINS.json').read_text())
    for rel, expected in pins.items():
        if sha(ROOT/rel) != expected: raise ValueError('Protected numerical source changed: '+rel)
    raw = (HERE/'profiled.yaml').read_bytes()
    blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    if blob != H36_BLOB: raise ValueError('Wrong H36 published YAML')
    base, read = profile(); alt, read2 = profile(HERE/'profiled.yaml')
    diff = {k:(asdict(base)[k], v) for k,v in asdict(alt).items() if asdict(base)[k]!=v}
    assert set(diff) == {'total_motor_torque_nm','max_power_w','max_brake_force_n'}
    return dict(protected_sha256=pins,h36_profile_blob=blob,h36_profile_sha256=sha(HERE/'profiled.yaml'),
                changed_coefficients=diff,baseline=asdict(base),h36=asdict(alt),readout=asdict(read))


class DevelopmentStore(ev.ex.Store):
    """Only development measurement payloads; role check precedes filesystem/SQL IO."""
    def load(self, bag: str, purpose: str):
        if purpose != 'development' or bag not in self.records or self.records[bag]['split'] != purpose or bag not in self.plan['splits'][purpose]:
            raise PermissionError('H43 only permits original development bags')
        r = self.records[bag]; path = self.root/bag/(bag+'_0.db3')
        if sha(path) != r['sha256']: raise ValueError('DB checksum mismatch: '+bag)
        allowed = list(ev.ex.CHANNELS)+list(ev.ex.REFS)
        access = dict(bag=bag,purpose=purpose,topics=allowed,sha256=r['sha256'],readonly=True)
        self.access.append(access)
        events, refs = [], {'master':[], 'rover':[]}
        origin = r['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            topics = [x[0] for x in con.execute('SELECT name FROM topics')]
            access['kinematic_state_topic_present'] = '/localization/kinematic_state' in topics
            query = ('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                     'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(query,allowed):
                stamp,values = ev.decode(raw,typ); t=(stamp-origin)/1e9
                if topic in ev.ex.CHANNELS:
                    ch=ev.ex.CHANNELS[topic]
                    events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed): refs[ev.ex.REFS[topic]].append((t,speed))
        return np.asarray(events,float), refs
