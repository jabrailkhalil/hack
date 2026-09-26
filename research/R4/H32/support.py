"""Pinned v8 research I/O. No validation or test measurement loader."""
from pathlib import Path
import sys, json, hashlib, sqlite3, math, os, platform, datetime
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'tools/finalization'), str(ROOT/'src/reserve_odometry')]
import evaluate as ev
from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.timeline import Timeline
np = ev.np
BASE = 'e3b0c9c039d2953fbfcda51231263d38ef9f1024'
TREE = 'eae49a504bc59b5c9b408445150bef32e111956f'
OPS = dict(rate_hz=20., alignment_delay_s=0.)

def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def profile():
    p = json.loads((ROOT/'src/reserve_odometry/config/champion_v8.json').read_text())
    actual, readout = {}, {}
    for line in (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text().splitlines():
        key, sep, value = line.strip().partition(':')
        if sep and key.startswith('model.'): actual[key[6:]] = float(value)
        if sep and key.startswith('readout.'): readout[key[8:]] = float(value)
    if actual != p['config'] or readout != p['readout']: raise ValueError('YAML/JSON mismatch')
    assert readout == dict(gain=1., holdoff_s=.5)
    assert actual['adaptation_tau_s'] == .5 and actual['common_mode_quarantine_s'] == 1.5
    assert actual['wheel_time_compensation'] == 0
    return Config(**actual), ReadoutConfig(**readout)

def baseline(config=None):
    c, r = profile()
    return GuardedReadoutObserver(config or c, readout=r)

def provenance():
    paths = ['src/reserve_odometry/reserve_odometry/'+n+'.py' for n in
             ['core','guarded_readout','timeline','node','guarded_node']]
    paths += ['src/reserve_odometry/config/champion_v8.'+s for s in ['yaml','json']]
    paths += ['tools/finalization/evaluate.py','tools/research_v3/experiment.py',
              'tools/research_v3/manifest.py','tools/research_guarded/compare.py',
              'tools/research_h11/compare.py','tools/export_bags.py',
              'research/plan_v3.json','research/split_v3.json']
    receipt = json.loads((Path(__file__).parent/'BASELINE.json').read_text())
    expected = {r['path']: r['sha256'] for r in receipt['files']}
    hashes = {p:sha(ROOT/p) for p in paths}
    for p,h in hashes.items():
        if expected[p] != h: raise ValueError('Protected baseline changed: '+p)
    c,r = profile()
    return dict(baseline_sha=BASE, baseline_tree=TREE, source_status='VERIFIED',
        protected_sha256=hashes, config=vars(c), readout=vars(r), operational=OPS,
        observer_class=GuardedReadoutObserver.__name__,
        module_file=sys.modules[GuardedReadoutObserver.__module__].__file__,
        source_ref=os.environ.get('GITHUB_SHA'), python=platform.python_version(),
        numpy=np.__version__, created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        validation_opened=False, test_opened=False)

class Store(ev.ex.Store):
    def __init__(self, journal, root=None):
        super().__init__(root or ROOT/'dataset/data'); self.journal=Path(journal)
    def load(self, bag, purpose):
        rec=self.records[bag]
        if purpose not in ('train','development') or rec['split'] != purpose:
            raise PermissionError('R4-H32 role denied before measurement I/O')
        path=self.root/bag/(bag+'_0.db3')
        allowed=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if purpose=='development' else [])
        entry=dict(bag=bag,purpose=purpose,topics=allowed,sha256=rec['sha256'],status='REQUESTED')
        self.access.append(entry); save(self.journal,self.access)
        if sha(path) != rec['sha256']: raise ValueError('Bag checksum mismatch: '+bag)
        events=[];refs={'master':[],'rover':[]}; origin=rec['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            query=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(query,allowed):
                stamp,values=ev.decode(raw,typ); t=(stamp-origin)/1e9
                if topic in ev.ex.CHANNELS:
                    ch=ev.ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed): refs[ev.ex.REFS[topic]].append((t,speed))
        entry['status']='LOADED';save(self.journal,self.access)
        return np.asarray(events,float),refs
