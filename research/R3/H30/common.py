"""Pinned v8 and role-checked development IO. No final/validation loader."""
from pathlib import Path
import hashlib, json, math, sqlite3, sys
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'src/reserve_odometry'), str(ROOT/'tools/finalization'), str(ROOT/'tools/research_guarded')]
import evaluate as ev
import compare as legacy
from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
import numpy as np
BASELINE = 'e3b0c9c039d2953fbfcda51231263d38ef9f1024'
OPS = dict(rate_hz=20., alignment_delay_s=0.)
HERE = Path(__file__).resolve().parent

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def verify():
    pin=json.loads((HERE/'BASELINE.json').read_text())
    assert pin['baseline_sha']==BASELINE
    for p,h in pin['sha256'].items():
        if sha(ROOT/p)!=h: raise ValueError('Pinned baseline modified: '+p)
    return pin

def profile():
    verify(); values={}
    for line in (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text().splitlines():
        k,sep,v=line.strip().partition(':')
        if sep and k.startswith(('model.','readout.')): values[k]=float(v)
    c={k[6:]:v for k,v in values.items() if k.startswith('model.')}
    r={k[8:]:v for k,v in values.items() if k.startswith('readout.')}
    assert c['common_mode_quarantine_s']==1.5 and c['wheel_time_compensation']==0.
    assert c['adaptation_tau_s']==.5 and r=={'gain':1.,'holdoff_s':.5}
    return Config(**c),ReadoutConfig(**r)

def baseline():
    c,r=profile();return GuardedReadoutObserver(c,readout=r)

def load(bag, journal, *, reference=False):
    store=ev.ex.Store()
    if bag not in store.plan['splits']['development'] or store.records[bag]['split']!='development':
        raise PermissionError('H30 permits development only')
    row=store.records[bag]; path=store.root/bag/(bag+'_0.db3')
    topics=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if reference else [])
    save(journal,dict(bag=bag,role='development',topics=topics,sha256=row['sha256'],reference=reference))
    if sha(path)!=row['sha256']:raise ValueError('DB hash mismatch')
    events=[];refs={'master':[],'rover':[]};origin=row['sensor_start_ns']
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
        query=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
               'WHERE t.name IN ('+','.join('?' for _ in topics)+') ORDER BY m.timestamp,m.id')
        for topic,typ,raw in con.execute(query,topics):
            stamp,values=ev.decode(raw,typ);t=(stamp-origin)/1e9
            if topic in ev.ex.CHANNELS:
                ch=ev.ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
            else:
                speed=math.hypot(float(values[0]),float(values[1]))
                if math.isfinite(speed):refs[ev.ex.REFS[topic]].append((t,speed))
    return np.asarray(events,float),refs,row['group']

def predict(events, observer, fault=None):
    old=ev.Observer
    try:
        ev.Observer=lambda c:observer
        return ev.replay(events,observer.c,OPS,fault)
    finally: ev.Observer=old
