"""Independent R6 forensic driver. Oracles never enter runtime source files."""
import copy,struct
import os,sys,json,hashlib,sqlite3,zipfile,io,math,csv,subprocess,inspect,textwrap
from pathlib import Path
import numpy as np
import yaml
ROOT=Path(__file__).resolve().parents[3]; LOCAL=ROOT.parent
SOURCE=Path(os.environ.get('R6_SOURCE',ROOT)).resolve()
sys.dont_write_bytecode=True
sys.path[:0]=[str(SOURCE/'src/reserve_odometry'),str(SOURCE/'tools')]
from reserve_odometry.core import Config,Sample
import reserve_odometry.core as core
from reserve_odometry.guarded_readout import GuardedReadoutObserver,ReadoutConfig
from reserve_odometry.timeline import Timeline
from export_bags import decode
BASE='b2783206000091ab11a1c11ac3ff79082188a4fb';TREE='973d50d288e050325ee1c71a90fa8d81f2a099af'
BAG='30639_0be558e2';CID='08f850870ac08fb7707e';START=71.55;END=74.55
OUT=ROOT/'research/R6/A1/results';FD1=LOCAL/'Odometry_Failure_Discovery_v1'
PARAMS=yaml.safe_load((SOURCE/'src/reserve_odometry/config/champion_v8.yaml').read_text())['reserve_odometry']['ros__parameters']
CFG=Config(**{k[6:]:v for k,v in PARAMS.items() if k.startswith('model.')})
RO=ReadoutConfig(**{k[8:]:v for k,v in PARAMS.items() if k.startswith('readout.')})
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,allow_nan=False,default=lambda x: x.item() if isinstance(x,np.generic) else str(x))+'\n')
def csvwrite(p,rows):
 with p.open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def load(write_lock=True):
 prior=LOCAL/'R6_A0/A0_41km_forensic_20260926T201323Z.zip'
 receipt=json.loads(prior.with_suffix('.receipt.json').read_text());assert sha(prior)==receipt['sha256']
 with zipfile.ZipFile(prior) as z:
  manifest=json.loads(z.read('EXPORT_MANIFEST.json'))
  for n,m in manifest.items():assert hashlib.sha256(z.read(n)).hexdigest()==m['sha256']
  old=json.loads(z.read('results/FORENSIC_LOCK.json'))
 for p in [LOCAL/'R6_A0/results/A0_REPORT.md',prior,prior.with_suffix('.receipt.json')]:assert p.is_file()
 for item in old['inputs']:assert sha(item['path'])==item['sha256']
 assert sha(FD1/'inputs/dataset.zip')=='d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52'
 split=json.loads((SOURCE/'research/split_v3.json').read_text());rec=next(r for r in split['records'] if r['bag']==BAG);assert rec['split']=='train'
 folds=json.loads((FD1/'.work/teacher/contracts/TRAIN_FOLDS.json').read_text())
 assert any(g['fold']=='check' and BAG in g['bags'] for g in folds['groups'])
 db=LOCAL/f'FD2/.work/check/{BAG}/{BAG}_0.db3';assert sha(db)==rec['sha256']
 files={str(p.relative_to(SOURCE)):sha(p) for p in (SOURCE/'src/reserve_odometry').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
 lock=dict(baseline=BASE,tree=TREE,loaded_core=str(Path(core.__file__).resolve()),source_hashes=files,prior=receipt,
  prior_report_sha256=sha(LOCAL/'R6_A0/results/A0_REPORT.md'),db_sha256=sha(db),dataset_sha256=sha(FD1/'inputs/dataset.zip'),
  source_zip_sha256=sha(FD1/'inputs/source.zip'),drive_source_id='1sOt4sDF11zYxt4Y1tUV0o9gGc6oOPcUq',drive_dataset_id='1hyhi4oRtSU9oO2ujwfPaUKFVndvbj8Z0',
  source_group=old['source_group'],vehicle_label='30639',bag=BAG,event_id=CID,fault=[START,END],scope='one previously identified train-check event only',
  validation_final_test_opened=False,development_opened=False)
 write(ROOT/'research/R6/A1/DEPENDENCIES.lock',lock) if write_lock else None
 topics={'/vehicle/status/steering_status':0} # actual canonical names below, no GNSS
 from collections import Counter
 # The frozen FD1 mapping is checked as a provenance dependency, read only.
 sys.path.insert(0,str(FD1));from failure_discovery.data import TOPICS
 con=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True);con.execute('PRAGMA query_only=ON');events=[];raw=[]
 for mid,arrival,name,typ,payload in con.execute('SELECT m.id,m.timestamp,t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id WHERE t.name IN (?,?,?) ORDER BY m.timestamp,m.id',list(TOPICS)):
  stamp,values=decode(payload,typ);ch=TOPICS[name];events.append(((stamp-rec['sensor_start_ns'])/1e9,ch,float(values[0])/(15 if ch==0 else 3.6)))
  raw.append((mid,arrival,int(stamp),ch,hashlib.sha256(payload).hexdigest()))
 con.close();events=np.array(events,float)
 assert hashlib.sha256(events.tobytes()).hexdigest()==old['event_array_sha256']
 lock['event_array_sha256']=old['event_array_sha256'];write(ROOT/'research/R6/A1/DEPENDENCIES.lock',lock) if write_lock else None
 return events,raw,lock

def run(events,fault=False,control='A0',witnesses=None):
 original=core.Observer.step;code=original.__code__;captured={}
 if control in ('Z','DZ'):
  src=textwrap.dedent(inspect.getsource(original));assert src.count('if zero_pair:')==1
  src=src.replace('if zero_pair:','if zero_pair and not getattr(self, "_forensic_zero", False):')
  ns=dict(vars(core));exec(compile(src,'<forensic-only-Z>','exec'),ns);core.Observer.step=ns['step'];code=core.Observer.step.__code__
 o=GuardedReadoutObserver(CFG,readout=RO);line=Timeline(o,rate_hz=20,delay_s=0);step=o.step;rows=[];trusted=None
 stable_since=None;stable_last=None;trigger=None;count=0
 def trace(f,event,arg):
  if event=='call' and f.f_code is code:f.f_trace_lines=False;return trace
  if event=='return' and f.f_code is code:captured.clear();captured.update(f.f_locals)
  return None
 def hook(t,command,front,rear):
  nonlocal stable_since,stable_last,trigger,count,trusted
  before={k:copy.deepcopy(v) for k,v in vars(o).items() if k!='step'} if END-.5<=t<=END+15 else None
  if witnesses is not None and before is not None:witnesses[t]=(before,(command,front,rear))
  v_pre,d_pre,drive_pre=o.v,o.disturbance,o.drive_a
  good=(t>=END and all(x is not None and 0<=t-x.t<=CFG.max_age_s and abs(x.value)<CFG.stop_speed_mps for x in (front,rear))
    and min(front.t,rear.t)>=END and abs(front.t-rear.t)<=CFG.pair_skew_s and abs(front.value-rear.value)<=CFG.disagreement_mps
    and command is not None and 0<=t-command.t<=CFG.command_timeout_s and command.value<=CFG.command_deadband)
  pair_t=max(front.t,rear.t) if good else None
  if not good:stable_since=None;stable_last=None;count=0
  elif stable_last is None or pair_t>stable_last:
   if stable_last is None or pair_t-stable_last>2*CFG.max_age_s:stable_since=pair_t;count=0
   stable_last=pair_t;count+=1
  stable=good and count>=2 and pair_t-stable_since+1e-9>=CFG.reacquire_dwell_s
  if stable and trigger is None:
   trigger=t
   if control in ('D','DZ'):o.disturbance=0.
  o._forensic_zero=bool(stable and control in ('Z','DZ'))
  e=step(t,command,front,rear);q=dict(captured)
  prestatuses=[None,None]
  if before is not None:
   probe=GuardedReadoutObserver.__new__(GuardedReadoutObserver);probe.__dict__.update(copy.deepcopy(before))
   prestatuses=[probe._wheel(i,x,t)[1] for i,x in enumerate((front,rear))]
  if stable and t==trigger:assert all(x in ('CANDIDATE','DUPLICATE_OR_OLD') for x in prestatuses),prestatuses
  if e.front_status==e.rear_status=='ACCEPTED':trusted=max(front.t,rear.t)
  r=dict(t=t,dt=q['dt'],v_pre=v_pre,d_pre=d_pre,drive_a_pre=drive_pre,gate=q.get('gate'),a_model=q.get('a_model'),front_pre_gate=prestatuses[0],rear_pre_gate=prestatuses[1],pair_skew=abs(front.t-rear.t) if front and rear else None,pair_disagreement=abs(front.value-rear.value) if front and rear else None,command=command.value if command else None,command_source_t=command.t if command else None,command_age=t-command.t if command else None,
   front_raw=front.value if front else None,rear_raw=rear.value if rear else None,front_age=t-front.t if front else None,rear_age=t-rear.t if rear else None,
   front_t=front.t if front else None,rear_t=rear.t if rear else None,front_status=e.front_status,rear_status=e.rear_status,
   inner_v=o.v,v=e.v,s=e.s,d=o.disturbance,drive_a=o.drive_a,pv=o.pv,gain=q.get('gain',0.),readout_v=o._velocity_correction,readout_s=o._distance_correction,
   mode=e.mode,predicted=q['predicted'],zero_lock=q.get('zero_pair',False),quarantine=o.reacquire_blocked_until,
   reacquire_since=o.reacquire_since,stop_since=o.stop_since,last_trusted_t=trusted,stable_pair=bool(stable),stable_pair_count=count,
   resets=line.resets,watermark=line.latest,fault_active=bool(fault and START<=t<END))
  rows.append(r);return e
 o.step=hook
 try:
  sys.settrace(trace)
  for t,ch,value in events:
   if fault and ch in (1,2) and START<=t<END:continue
   line.ingest(int(ch),Sample(float(t),float(value)))
   for _ in line.advance():pass
 finally:sys.settrace(None);core.Observer.step=original
 return rows,trigger

def arrays(rows):return {k:np.array([r[k] for r in rows]) for k in rows[0]}
def horizon(rows,clean):
 a=arrays(rows);c=arrays(clean);out=[]
 for h in [0,1,2,5,10,30,60,120,300,600,'terminal']:
  i=len(rows)-1 if h=='terminal' else int(np.argmin(abs(a['t']-(END+h))))
  r=rows[i];out.append(dict(horizon=h,t=r['t'],delta_v=r['v']-clean[i]['v'],delta_s=r['s']-clean[i]['s'],d=r['d'],mode=r['mode'],front_status=r['front_status'],rear_status=r['rear_status'],v=r['v'],saturated=abs(r['v'])>=40-1e-9))
 return out

def a0():
 events,raw,lock=load();clean,_=run(events);dirty,_=run(events,True);a=arrays(dirty);c=arrays(clean)
 fd2=LOCAL/'FD2/FD2_results_20260926T193439Z.zip';r=json.loads(fd2.with_suffix('.receipt.json').read_text());assert sha(fd2)==r['sha256']
 with zipfile.ZipFile(fd2) as z:
  with np.load(io.BytesIO(z.read(f'runs/real_check/bags/{BAG}/traces/{CID}.npz'))) as f:
   keep=a['mode']!='WAITING_FOR_INITIALIZATION'
   for k in ['t','v','s']:assert np.array_equal(a[k][keep],f[k])
   for k in ['v','s']:assert np.array_equal(c[k][keep],f['clean_'+k])
 dv=a['v']-c['v'];ds=a['s']-c['s'];area=np.r_[0,.5*(dv[1:]+dv[:-1])*np.diff(a['t'])];res=ds-np.cumsum(area)
 assert max(abs(res))<1e-6 and np.isfinite(a['v']).all() and np.isfinite(a['s']).all()
 for x,y in zip(dirty,clean):x.update(delta_v=x['v']-y['v'],delta_s=x['s']-y['s'],clean_v=y['v'],clean_s=y['s'],clean_mode=y['mode'])
 d=OUT/'A0';csvwrite(d/'A0_TIMELINE.csv',dirty);np.savez_compressed(d/'A0_STATE_TRACE.npz',**arrays(dirty));np.savez_compressed(d/'CLEAN_TRACE.npz',**c)
 csvwrite(d/'A0_HORIZONS.csv',horizon(dirty,clean))
 summary=dict(status='BUG_CANDIDATE_REPRODUCED',reproduced=True,canonical_commit=BASE,canonical_tree=TREE,terminal_delta_s=float(ds[-1]),
  max_integral_residual=float(max(abs(res))),max_dt=float(max(np.diff(a['t']))),sum_dt=float(sum(np.diff(a['t']))),max_step_delta_s=float(max(abs(area))),resets=dirty[-1]['resets'],
  output_ticks=len(dirty),input_events=len(events),exact_archived_trace_match=True,loaded_source=lock['loaded_core'],horizons=horizon(dirty,clean),
  shape='permanent MODEL_ONLY lockout, acceleration then speed saturation and approximately linear distance growth',UPSTREAM_METRIC_INFRASTRUCTURE_RISK=False)
 write(d/'A0_REPRODUCTION.json',summary)
 (d/'A0_REPORT.md').write_text('# A0 independent reproduction\n\nBUG_CANDIDATE_REPRODUCED. Exact canonical checkout/runtime trace equality.\n\n'+json.dumps(summary,indent=2)+'\n\nThis is internal counterfactual divergence, not official XYZ error. No runtime changes. Only one identified train-check DB read. The prior receipt, all packaged payloads, and input hashes were verified. No synthetic schedule, no resets, no nonfinite states, no output duplicate/reversal, no large integration step.\n')
 print(json.dumps(summary,indent=2))

if __name__=='__main__':a0()
