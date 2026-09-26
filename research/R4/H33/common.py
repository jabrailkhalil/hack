"""R4-H33 isolated factory/role adapter. Published scorers are imported unchanged."""
import hashlib, importlib.util, json, math, os, sqlite3, subprocess, sys
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tools/finalization'), str(ROOT/'src/reserve_odometry')]
import evaluate as ev
from reserve_odometry.core import Config, Observer, Sample, clip
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
np=ev.np
BASE='e3b0c9c039d2953fbfcda51231263d38ef9f1024'
OPS={'rate_hz':20., 'alignment_delay_s':0.}
PHYSICAL=('total_motor_torque_nm','max_power_w','max_brake_force_n','rolling_force_n','quadratic_drag_n_s2_m2','command_exponent','actuator_tau_s')
def module(name, path):
    spec=importlib.util.spec_from_file_location(name, ROOT/path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
gc=module('h33_guarded','tools/research_guarded/compare.py')
v6=module('h33_v6','tools/research_v6/compare.py')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def profile():
    cfg={};rd={};ops={}
    for line in (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text().splitlines():
        k,sep,v=line.strip().partition(':')
        if sep and k.startswith('model.'):cfg[k[6:]]=float(v)
        if sep and k.startswith('readout.'):rd[k[8:]]=float(v)
        if sep and k in OPS:ops[k]=float(v)
    c=Config(**cfg)
    assert set(asdict(c))==set(cfg), 'Missing model fields: cannot use defaults'
    assert ops==OPS and rd=={'gain':1.,'holdoff_s':.5}
    assert c.common_mode_quarantine_s==1.5 and c.wheel_time_compensation==0 and c.adaptation_tau_s==.5
    return c,ReadoutConfig(**rd)
def baseline(c=None):return GuardedReadoutObserver(c or profile()[0],readout=profile()[1])
def integrity():
    tree=subprocess.check_output(['git','rev-parse',BASE+'^{tree}'],cwd=ROOT,text=True).strip()
    assert tree=='eae49a504bc59b5c9b408445150bef32e111956f'
    listing=subprocess.check_output(['git','ls-tree','-r','-z',BASE],cwd=ROOT).split(b'\0')
    pins={}
    for item in listing:
        if not item:continue
        meta,path=item.split(b'\t',1);mode,typ,blob=meta.decode().split();f=path.decode()
        raw=(ROOT/f).read_bytes()
        actual=hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest()
        if actual!=blob:raise ValueError('Pinned blob changed: '+f)
        executable=bool((ROOT/f).stat().st_mode & 0o111)
        if executable!=(mode=='100755'):raise ValueError('Pinned executable bit changed: '+f)
        pins[f]=hashlib.sha256(raw).hexdigest()
    if len(pins)!=301:raise ValueError('Incomplete baseline')
    return dict(baseline_sha=BASE,baseline_tree=tree,count=len(pins),pins=pins)

class Store(ev.ex.Store):
    def __init__(self, journal):super().__init__();self.journal=Path(journal)
    def load(self,bag,purpose):
        r=self.records[bag]
        if purpose not in ('train','development','validation') or r['split']!=purpose:raise PermissionError('Role denied before IO')
        if purpose=='validation' and not os.environ.get('H33_FREEZE_COMMIT'):raise PermissionError('Validation locked')
        topics=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if purpose!='train' else [])
        self.access.append(dict(bag=bag,purpose=purpose,sha256=r['sha256'],topics=topics,read_only=True))
        save(self.journal,dict(test_evaluated=False,access=self.access))
        path=self.root/bag/(bag+'_0.db3')
        if sha(path)!=r['sha256']:raise ValueError('Bag checksum mismatch')
        events=[];refs={'master':[],'rover':[]};origin=r['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            q=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id WHERE t.name IN ('+','.join('?' for _ in topics)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(q,topics):
                stamp,values=ev.decode(raw,typ);t=(stamp-origin)/1e9
                if topic in ev.ex.CHANNELS:
                    ch=ev.ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed):refs[ev.ex.REFS[topic]].append((t,speed))
        return np.asarray(events,float),refs

def score(events,refs,factories,fault=None):
    """Only Observer factory is dispatched; ev.score/replay/matching are untouched."""
    configs={name:profile()[0] for name in factories};lookup={id(configs[n]):f for n,f in factories.items()}
    original=ev.Observer
    try:
        ev.Observer=lambda c:lookup[id(c)](c)
        return ev.score(events,refs,configs,OPS,fault)
    finally:ev.Observer=original
