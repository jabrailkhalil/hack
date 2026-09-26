"""H38 role adapter. Original SQL, decoder and evaluator are unchanged."""
from pathlib import Path
import sys, json, math, hashlib, sqlite3
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/finalization'))
import evaluate as ev
import numpy as np
from reserve_odometry.core import Config, Sample, clip
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig

BASELINE='e3b0c9c039d2953fbfcda51231263d38ef9f1024'
TREE='eae49a504bc59b5c9b408445150bef32e111956f'
PLAN_SHA='0ef87ffc830dab9401128b927c183bda9a53b397'
OPS=dict(rate_hz=20.,alignment_delay_s=0.)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def profile():
    raw={}
    for line in (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text().splitlines():
        k,sep,v=line.strip().partition(':')
        if sep and (k.startswith('model.') or k.startswith('readout.') or k in OPS):raw[k]=float(v)
    cfg={k[6:]:v for k,v in raw.items() if k.startswith('model.')}
    rd={k[8:]:v for k,v in raw.items() if k.startswith('readout.')}
    from dataclasses import asdict
    assert asdict(Config(**cfg))==cfg, 'Do not use implicit Config defaults'
    assert rd==dict(gain=1.,holdoff_s=.5)
    assert {k:raw[k] for k in OPS}==OPS
    return cfg,rd

def baseline():
    cfg,rd=profile();return GuardedReadoutObserver(Config(**cfg),readout=ReadoutConfig(**rd))

class RoleStore(ev.ex.Store):
    """No test/validation access in this development runner, before hash or IO."""
    def load(self,bag,purpose):
        record=self.records[bag]
        if purpose not in ('train','development') or record['split']!=purpose:
            raise PermissionError('H38 role denied before IO: '+bag+'/'+purpose)
        if purpose=='train':return super().load(bag,purpose)
        path=self.root/bag/(bag+'_0.db3')
        if ev.ex.digest(path)!=record['sha256']:raise ValueError('Checksum mismatch '+bag)
        allowed=list(ev.ex.CHANNELS)+list(ev.ex.REFS)
        events=[];refs={'master':[],'rover':[]};origin=record['sensor_start_ns']
        self.access.append(dict(bag=bag,purpose=purpose,topics=allowed,sha256=record['sha256']))
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            query=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                   'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(query,allowed):
                stamp,values=ev.ex.decode(raw,typ);t=(stamp-origin)/1e9
                if topic in ev.ex.CHANNELS:
                    ch=ev.ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed):refs[ev.ex.REFS[topic]].append((t,speed))
        return np.asarray(events,float),refs
