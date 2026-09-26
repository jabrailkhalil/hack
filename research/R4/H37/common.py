"""R4-H37 standalone driver support; no edits to the pinned scorer/runtime."""
from pathlib import Path
import hashlib, importlib.util, json, math, os, sqlite3, sys
from dataclasses import asdict, fields
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT/'tools/finalization'), str(ROOT/'src/reserve_odometry')]
import evaluate as ev
from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
np = ev.np
BASELINE = 'e3b0c9c039d2953fbfcda51231263d38ef9f1024'
PLAN_SHA = '8d14f9177271a258d1ad280352c61241e4b17e76'
OPS = dict(rate_hz=20., alignment_delay_s=0.)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n')

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m

group = module('h37_group', ROOT/'tools/research_v6/compare.py')
guarded = module('h37_guarded', ROOT/'tools/research_guarded/compare.py')
h11 = module('h37_h11', ROOT/'tools/research_h11/compare.py')

def profile():
    p={}
    for line in (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text().splitlines():
        k,sep,v=line.strip().partition(':')
        if sep and k.startswith(('model.','readout.')):p[k]=float(v.strip())
    c={k[6:]:v for k,v in p.items() if k.startswith('model.')}
    r={k[8:]:v for k,v in p.items() if k.startswith('readout.')}
    ref=json.loads((ROOT/'src/reserve_odometry/config/champion_v8.json').read_text())
    assert c==ref['config'] and r==ref['readout']
    assert set(c)=={f.name for f in fields(Config)}
    assert c['common_mode_quarantine_s']==1.5 and c['adaptation_tau_s']==.5
    assert c['wheel_time_compensation']==0 and r==dict(gain=1.,holdoff_s=.5)
    return Config(**c),ReadoutConfig(**r)

def pins():
    expected=json.loads((HERE/'BASE_PINS.json').read_text())
    # This hashes bytes, including immutable archives, but does not parse historical metrics.
    errors=[p for p,s in expected.items() if sha(ROOT/p)!=s]
    if errors:raise ValueError('Baseline bytes changed: '+str(errors))
    import reserve_odometry.core as core
    return dict(baseline_sha=BASELINE,baseline_tree='eae49a504bc59b5c9b408445150bef32e111956f',
        verified_baseline_files=len(expected),baseline_hashes=expected,plan_commit=PLAN_SHA,
        measured_source_sha=os.getenv('H37_MEASURED_SHA'),
        local_source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(HERE.rglob('*.py'))},
        baseline_module=core.__file__,baseline_class='GuardedReadoutObserver',
        config=asdict(profile()[0]),readout=asdict(profile()[1]),ops=OPS,
        python=sys.version,numpy=np.__version__,validation_opened=False,test_opened=False)

class Store(ev.ex.Store):
    """Preserve real roles; check role and checksum before read-only SQL."""
    def __init__(self,journal=None):
        super().__init__(Path(os.getenv('H37_DATA_ROOT',ROOT/'dataset/data')))
        self.journal=journal
    def load(self,bag,purpose):
        row=self.records[bag]
        if purpose not in ('train','development') or row['split']!=purpose:
            raise PermissionError('Only true train/development allowed: '+bag+'/'+purpose)
        path=self.root/bag/(bag+'_0.db3')
        if sha(path)!=row['sha256']:raise ValueError('Checksum: '+bag)
        allowed=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if purpose=='development' else [])
        self.access.append(dict(bag=bag,role=purpose,topics=allowed,sha256=row['sha256']))
        if self.journal:save(self.journal,self.access)
        events=[];refs={'master':[],'rover':[]};origin=row['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            sql=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                 'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(sql,allowed):
                stamp,values=ev.decode(raw,typ);t=(stamp-origin)/1e9
                if topic in ev.ex.CHANNELS:
                    ch=ev.ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed):refs[ev.ex.REFS[topic]].append((t,speed))
        return np.asarray(events,float),refs

def targets(c,u,v):
    q=min(1.,max(0.,(abs(u)-c.command_deadband)/(1-c.command_deadband)))**c.command_exponent
    f=c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m
    cap=c.max_power_w/max(abs(v),1.)
    return q,f,cap,c.travel_direction*q*min(f,cap)/c.mass_kg,c.travel_direction*min(q*f,cap)/c.mass_kg

def baseline(c):return GuardedReadoutObserver(c,readout=profile()[1])

def replay(events,factory,fault=None):
    previous=ev.Observer
    try:
        ev.Observer=factory
        return ev.replay(events,profile()[0],OPS,fault)
    finally:ev.Observer=previous
