"""R4-H35 source identity, exact canonical profile, allowed role loader."""
from pathlib import Path
import hashlib, importlib.util, json, math, os, sqlite3, subprocess, sys
from dataclasses import asdict, fields
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'src/reserve_odometry'),str(ROOT/'tools/finalization')]
import evaluate as ev
from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
np=ev.np
BASELINE='e3b0c9c039d2953fbfcda51231263d38ef9f1024'
TREE='eae49a504bc59b5c9b408445150bef32e111956f'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def load_module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
 sys.modules[name]=m;spec.loader.exec_module(m);return m
legacy=load_module('h35_legacy_summary',ROOT/'tools/research_v6/compare.py')
guarded=load_module('h35_guarded_windows',ROOT/'tools/research_guarded/compare.py')
# H11 uses the module name compare for the pinned guarded evaluator.
sys.modules['compare']=guarded
h11=load_module('h35_h11',ROOT/'tools/research_h11/compare.py')
def profile():
 d={}
 for line in (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text().splitlines():
  k,s,v=line.strip().partition(':')
  if s and v.strip() and not k.startswith('#'):
   try:d[k]=float(v.strip())
   except ValueError:pass
 cfg={k[6:]:v for k,v in d.items() if k.startswith('model.')}
 assert set(cfg)=={f.name for f in fields(Config)},'incomplete canonical profile'
 ro={k[8:]:v for k,v in d.items() if k.startswith('readout.')}
 assert d['rate_hz']==20 and d['alignment_delay_s']==0
 assert cfg['common_mode_quarantine_s']==1.5 and cfg['adaptation_tau_s']==.5
 return Config(**cfg),ReadoutConfig(**ro)
OPS={'rate_hz':20.,'alignment_delay_s':0.}
def verify_sources():
 if (HERE/'SOURCE_RECEIPT.json').exists():
  receipt=json.loads((HERE/'SOURCE_RECEIPT.json').read_text())
 else:
  assert subprocess.check_output(['git','rev-parse',BASELINE+'^{tree}'],cwd=ROOT,text=True).strip()==TREE
  raw=subprocess.check_output(['git','ls-tree','-rz',BASELINE],cwd=ROOT)
  entries=[]
  for item in raw.split(b'\0'):
   if not item:continue
   meta,path=item.split(b'\t',1);mode,kind,blob=meta.decode().split();path=path.decode()
   value=(ROOT/path).read_bytes()
   actual=hashlib.sha1(f'blob {len(value)}\0'.encode()+value).hexdigest()
   assert actual==blob,path
   entries.append(dict(path=path,sha256=sha(ROOT/path)))
  receipt=dict(actual_git_tree=TREE,file_count=len(entries),files=entries)
 assert receipt['actual_git_tree']==TREE and receipt['file_count']==301
 bad=[r['path'] for r in receipt['files'] if not (ROOT/r['path']).exists() or sha(ROOT/r['path'])!=r['sha256']]
 if bad:raise ValueError('baseline source changed: '+repr(bad))
 return {r['path']:r['sha256'] for r in receipt['files']}
class Store(ev.ex.Store):
 """Separate explicit development loader; historical Store is never relaxed."""
 def __init__(self,data_root=None):
  super().__init__(data_root or os.environ.get('H35_DATA_ROOT',ROOT/'dataset/H35'))
 def load(self,bag,purpose):
  if purpose not in ('train','development'):raise PermissionError('H35 validation/test locked')
  row=self.records[bag]
  if row['split']!=purpose or bag not in self.plan['splits'][purpose]:raise PermissionError((bag,purpose))
  p=self.root/purpose/bag/(bag+'_0.db3')
  if sha(p)!=row['sha256']:raise ValueError('bag SHA256 '+bag)
  allowed=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if purpose=='development' else [])
  self.access.append(dict(bag=bag,purpose=purpose,sha256=row['sha256'],topics=allowed))
  events=[];refs={'master':[],'rover':[]};origin=row['sensor_start_ns']
  with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as con:
   q='SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id'
   for topic,typ,raw in con.execute(q,allowed):
    stamp,vals=ev.decode(raw,typ);t=(stamp-origin)/1e9
    if topic in ev.ex.CHANNELS:
     ch=ev.ex.CHANNELS[topic];events.append((t,ch,float(vals[0])/(15 if ch==0 else 3.6)))
    else:
     v=math.hypot(float(vals[0]),float(vals[1]))
     if math.isfinite(v):refs[ev.ex.REFS[topic]].append((t,v))
  return np.asarray(events,float),refs
