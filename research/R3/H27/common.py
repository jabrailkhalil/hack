"""Pinned sources, profile and strict role-only data access for R3-H27."""
import hashlib
import json
import math
import sqlite3
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = 'e3b0c9c039d2953fbfcda51231263d38ef9f1024'
sys.path[:0] = [str(ROOT/'tools/finalization'), str(ROOT/'src/reserve_odometry')]
import evaluate as ev
from reserve_odometry.core import Config
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
OPS = dict(rate_hz=20., alignment_delay_s=0.)


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, data):
    p=Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def profile():
    fields = {}
    for line in (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text().splitlines():
        key,sep,value=line.strip().partition(':')
        if sep and key.startswith(('model.','readout.')): fields[key]=float(value)
    cfg={k[6:]:v for k,v in fields.items() if k.startswith('model.')}
    readout={k[8:]:v for k,v in fields.items() if k.startswith('readout.')}
    if cfg.keys()!=Config.__dataclass_fields__.keys(): raise ValueError('Profile missing native fields')
    if cfg['common_mode_quarantine_s']!=1.5 or cfg['adaptation_tau_s']!=.5 or cfg['wheel_time_compensation']!=0:
        raise ValueError('Not canonical v8')
    if readout != dict(gain=1.,holdoff_s=.5): raise ValueError('Not canonical guarded readout')
    return Config(**cfg),ReadoutConfig(**readout)


def integrity():
    pins=json.loads((HERE/'PINS.json').read_text())
    for path,digest in pins.items():
        if sha(ROOT/path)!=digest: raise ValueError('Source mismatch: '+path)
    try:
        source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
        for path,digest in pins.items():
            raw=subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT)
            if hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('Pin not actual baseline: '+path)
    except subprocess.CalledProcessError:
        source='LOCAL_SOURCE_SNAPSHOT_NO_GIT_OBJECTS'
    profile()
    return dict(baseline=BASE, source=source, pinned= pins,
                code={str(p.relative_to(ROOT)):sha(p) for p in sorted(HERE.rglob('*.py'))},test_evaluated=False,validation_opened=False)


class VehicleStore(ev.ex.Store):
    """Train/development only. Never opens validation or test, or train GNSS."""
    def load(self,bag,purpose,reference=False):
        if purpose not in ('train','development'): raise PermissionError('Stage not allowed')
        row=self.records[bag]
        if row['split']!=purpose or bag not in self.plan['splits'][purpose]: raise PermissionError('Role mismatch')
        if reference and purpose!='development': raise PermissionError('Train GNSS is forbidden')
        path=self.root/bag/(bag+'_0.db3')
        if sha(path)!=row['sha256']: raise ValueError('DB checksum mismatch')
        allowed=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if reference else [])
        # Access record is constructed before read-only SQLite IO.
        self.access.append(dict(bag=bag,purpose=purpose,sha256=row['sha256'],topics=allowed))
        events=[];refs={'master':[],'rover':[]};origin=row['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            query=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                   'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(query,allowed):
                stamp,values=ev.decode(raw,typ);t=(stamp-origin)/1e9
                if topic in ev.ex.CHANNELS:
                    ch=ev.ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed): refs[ev.ex.REFS[topic]].append((t,speed))
        return ev.np.asarray(events,float),refs
