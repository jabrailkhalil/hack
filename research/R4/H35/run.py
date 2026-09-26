"""R4-H35 paired development. Original evaluator, explicit observer dispatch.

No fit or validation/test entry point. Results of both registered ratios are
retained. Metrics, fault locations and their aggregation remain pinned code.
"""
import argparse, csv, datetime, json, math, os, time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from common import *
from factory import build, runtime, enabled_identity
from foundation import episodes
RATIOS={'v8':None,'off':1.,'H35_R050':.5,'H35_R200':2.}
ALIASES={'baseline_v2':'v8','balanced_physics':'off'}
ORIGINAL_REPLAY=ev.replay

def array_hash(a):
 return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()

def signed_integral(a,target):
 good=np.isfinite(target)
 if len(a)<2:return None
 edge=good[1:]&good[:-1]&(np.diff(a[:,0])<=.051)
 if not np.any(edge):return None
 error=a[:,1]-target
 return float(np.sum(.5*(error[1:]+error[:-1])[edge]*np.diff(a[:,0])[edge]))

class Monitor:
 """External offline collector; it is NOT part of the runtime algorithm."""
 def __init__(self,observer):
  self.o=observer;self.local_release_changes=0;self.release_steps=0;self.steps=0;self.trace=[]
 def __getattr__(self,k):return getattr(self.o,k)
 def step(self,t,command=None,front=None,rear=None):
  o=self.o;dt=0. if o.t is None else t-o.t
  fresh=o._valid(command,t,o.c.command_timeout_s) and abs(command.value)<=1.000001
  u=max(-1.,min(1.,command.value)) if fresh else 0.
  target=o.drive_target(u,o.v);x=o.drive_a
  release=fresh and runtime.release_phase(x,target)
  if release and dt>0:
   self.release_steps+=1
   base=x+(1-math.exp(-dt/o.c.actuator_tau_s))*(target-x)
   alt=runtime.advance_release(x,target,dt,o.c.actuator_tau_s,getattr(o,'release_ratio',1.))
   if abs(alt-base)>1e-8:self.local_release_changes+=1
  e=o.step(t,command,front,rear);self.steps+=1
  if self.steps%10==0:
   self.trace.append((t,x,target,o.drive_a,o.disturbance,e.v,e.s,o.v,float(release),float(fresh)))
  return e

def paired(events,refs,fault=None,full=False,trace_path=None):
 """The replay wrapper only chooses the class and captures its output."""
 configs={k:profile()[0] for k in ('baseline_v2','balanced_physics','H35_R050','H35_R200')}
 labels={id(c):ALIASES.get(k,k) for k,c in configs.items()}
 arrays={};infos={};monitors={};old_observer,old_replay=ev.Observer,ev.replay
 def capture(e,c,ops,f=None):
  name=labels[id(c)];m=Monitor(build(RATIOS[name]));monitors[name]=m
  ev.Observer=lambda cfg:m
  a,info=ORIGINAL_REPLAY(e,c,ops,f);arrays[name]=a;infos[name]=info
  return a,info
 try:
  ev.replay=capture
  row=ev.score(events,refs,configs,OPS,fault)
 finally:
  ev.replay=old_replay;ev.Observer=old_observer
 a=arrays['v8'];t=a[:,0]
 assert np.array_equal(a,arrays['off'],equal_nan=True) and infos['v8']==infos['off'],'off parity'
 for b in arrays.values():assert b.shape==a.shape and np.array_equal(b[:,0],t),'schedule'
 for values in row['receivers'].values():
  for old,new in ALIASES.items():values[new]=values.pop(old)
 for old,new in ALIASES.items():row['runtime'][new]=row['runtime'].pop(old)
 row['provenance']=dict(input_sha256=array_hash(events),timestamps_sha256=array_hash(t),reference={})
 for receiver,values in refs.items():
  target=ev.ex.match(values,t);mask=np.isfinite(target)
  if fault:mask &= (t>=fault['start'])&(t<fault['end']+10.)
  row['provenance']['reference'][receiver]=dict(target_sha256=array_hash(target),mask_sha256=array_hash(mask),n=int(mask.sum()))
  for name,b in arrays.items():
   m=row['receivers'][receiver][name]
   if full or not fault:
    m['signed_integral_error_m']=signed_integral(b,target)
   if full:
    m['distance_surrogate']=ev.distance_surrogate(b,target)
    m['full_bag_metrics']=ev.ex.metrics(t,b[:,1],target,np.isfinite(target))
    m['full_bag_false_stops']=int(np.sum(np.isfinite(target)&(target>1)&(b[:,5]>0)))
 row['activation']={n:dict(release_steps=m.release_steps,local_release_changes=m.local_release_changes,
                          changed_speed_ticks=int(np.sum(np.abs(arrays[n][:,1]-a[:,1])>1e-8))) for n,m in monitors.items()}
 if full:
  row['distance_delta']={}
  for name,b in arrays.items():
   points={}
   for secs in (1,5,10):
    j=int(np.searchsorted(t,fault['end']+secs));points[str(secs)]=float(b[j,2]-a[j,2]) if j<len(t) else None
   row['distance_delta'][name]=dict(terminal_delta_s_m=float(b[-1,2]-a[-1,2]) if len(t) else None,post_end_delta_s_m=points)
 if trace_path is not None:
  trace_path.parent.mkdir(parents=True,exist_ok=True)
  np.savez_compressed(trace_path,**{n:np.asarray(m.trace,float).reshape(-1,10) for n,m in monitors.items()})
 return row

def low_windows(events):
 grid=ev.ex.grid_channels(events)
 if grid is None:return
 t,u,f,r,valid=grid
 ix=np.flatnonzero(valid&((f+r)/2>=1)&((f+r)/2<=2)&(np.abs(f-r)<.15)&(t>max(25.,.1*t[-1]))&(t<t[-1]-25))
 if len(ix):
  anchor=float(t[ix[0]]);fault=dict(kind='lock',start=anchor,end=anchor+5.)
  yield fault,events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+15.1)]

def phase_windows(events):
 es,_,_=episodes(events);used=set();end=events[:,0].max()
 for e in es:
  if e['t']<=25 or e['t']>=end-16 or e['kind'] in used:continue
  used.add(e['kind'])
  for offset in (-.2,.2):
   start=e['t']+offset;f=dict(kind='dropout',start=start,end=start+5.,release_kind=e['kind'],offset_s=offset)
   yield f,events[(events[:,0]>=start-20)&(events[:,0]<=start+15.1)]

def worker(args):
 bag,out=args;store=Store();events,refs=store.load(bag,'development');group=store.records[bag]['group']
 dest=out/'bags'/bag;dest.mkdir(parents=True,exist_ok=False)
 def record(row,suite,fault=None):return dict(bag=bag,group=group,suite=suite,**({'fault':fault} if fault else {}),**row)
 clean=record(paired(events,refs,trace_path=dest/'clean-trace.npz'),'clean')
 save(dest/'clean.json',clean)
 sets={'original':[],'low_speed':[],'common_mode':[],'release_diagnostic':[],'full_original':[]}
 for suite,generator in (('original',guarded.fault_windows),('low_speed',low_windows),('common_mode',h11.common_fault_windows),('release_diagnostic',phase_windows)):
  for j,(f,w) in enumerate(generator(events)):
   if suite=='common_mode':w=h11.inject_common(w,f)
   row=record(paired(w,refs,f,trace_path=dest/f'{suite}-{j}-trace.npz'),suite,f)
   sets[suite].append(row)
   if suite=='original':
    sets['full_original'].append(record(paired(events,refs,f,full=True),'full_original',f))
  save(dest/f'{suite}.json',sets[suite])
 save(dest/'full_original.json',sets['full_original']);save(dest/'access.json',store.access)
 print('DEVELOPMENT',bag,{k:len(v) for k,v in sets.items()},flush=True)
 return dict(clean=clean,**sets,access=store.access)

def relative(a,b):return a/b-1 if b else (0. if abs(a-b)<=1e-12 else None)
def exceeds(a,b,fraction):return a>b*(1+fraction)+1e-12

def safety_reasons(rows,name,clean=False):
 reasons=[]
 for row in rows:
  label=row['bag']+'/'+row['suite']+'/'+str(row.get('fault',{}).get('start',''))
  rt=row['runtime'][name]
  if rt['causal_errors'] or rt['resets']:reasons.append('causality_or_reset:'+label)
  for receiver,scores in row['receivers'].items():
   a,b=scores[name],scores['v8'];key=label+'/'+receiver
   if a['n']!=b['n'] or a['coverage']!=b['coverage']:reasons.append('coverage:'+key)
   if a.get('false_stop_samples',0)>b.get('false_stop_samples',0):reasons.append('false_stop:'+key)
   if a.get('full_bag_false_stops',0)>b.get('full_bag_false_stops',0):reasons.append('full_bag_false_stop:'+key)
   if b.get('event_rmse') is not None and b.get('recovery_s') is not None and a.get('recovery_s') is None:reasons.append('new_unrecovered:'+key)
   if clean and b['rmse'] is not None and (a['rmse'] is None or a['rmse']>b['rmse']+max(.005,.05*b['rmse'])):reasons.append('clean_bag_regression:'+key)
 return reasons

def decision(data):
 clean,stress=data['clean'],data['original']
 summaries={n:legacy.summary(clean,stress,n) for n in RATIOS}
 for n,s in summaries.items():
  for key in ('mae','bias','p95','signed_integral_error_m'):s['clean_'+key]=legacy.macro(clean,n,key)
  for key in ('mae','bias','p95','recovery_s'):s['fault_window_'+key]=legacy.macro(stress,n,key)
  for suite in ('low_speed','common_mode','release_diagnostic'):s[suite+'_rmse']=legacy.macro(data[suite],n,'event_rmse')
  s['full_fault_distance_rmse']=legacy.macro(data['full_original'],n,'distance')
 base=summaries['v8'];expected=dict(clean_rmse=.09266814298282507,fault_rmse=.2375486120563008,pooled_rmse=.1293056944774334,distance_rmse=5.310295004801444,samples=394221)
 for k,v in expected.items():
  if base[k] is None or abs(base[k]-v)>1e-10:raise ValueError(('baseline_fingerprint',k,base[k],v))
 candidates={}
 allrows=[r for key in ('original','low_speed','common_mode','release_diagnostic','full_original') for r in data[key]]
 for n in ('H35_R050','H35_R200'):
  s=summaries[n];reasons=safety_reasons(clean,n,True)+safety_reasons(allrows,n)
  changes={k:relative(s[k],base[k]) for k in ('clean_rmse','fault_rmse','pooled_rmse','distance_rmse','low_speed_rmse','common_mode_rmse','full_fault_distance_rmse')}
  if s['clean_rmse']>base['clean_rmse']*.98 and s['fault_rmse']>base['fault_rmse']*.95:reasons.append('insufficient_gain')
  for key,limit in (('clean_rmse',.005),('fault_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01),('low_speed_rmse',.005),('common_mode_rmse',.005),('full_fault_distance_rmse',.01)):
   if s[key] is None or base[key] is None:reasons.append('missing_metric:'+key)
   elif exceeds(s[key],base[key],limit):reasons.append('aggregate_regression:'+key)
  activation={k:sum(r['activation'][n][k] for r in clean) for k in ('local_release_changes','changed_speed_ticks')}
  groups={r['group'] for r in clean if r['activation'][n]['local_release_changes']>0 and r['activation'][n]['changed_speed_ticks']>0}
  activation['groups']=len(groups);activation['group_ids']=sorted(groups)
  if min(activation['local_release_changes'],activation['changed_speed_ticks'])<200 or len(groups)<3:reasons.append('insufficient_activation')
  candidates[n]=dict(eligible=not reasons,reasons=sorted(set(reasons)),relative_change=changes,activation=activation)
 eligible=[n for n,v in candidates.items() if v['eligible']]
 selected=min(eligible,key=lambda n:(round(summaries[n]['fault_rmse'],12),summaries[n]['clean_rmse'],RATIOS[n])) if eligible else None
 verdict='CONFIRMED_DEVELOPMENT' if selected else 'REJECTED'
 if not selected and all('insufficient_activation' in v['reasons'] and set(v['reasons'])<= {'insufficient_activation','insufficient_gain'} for v in candidates.values()):verdict='INCONCLUSIVE'
 return dict(verdict=verdict,selected=selected,summary=summaries,candidates=candidates,baseline_reproduced=True,validation_opened=False,test_opened=False,ready_to_merge=False)

def export_csv(data,out):
 with (out/'per_case.csv').open('w',newline='') as f:
  writer=csv.writer(f);writer.writerow(['bag','group','suite','fault','duration_s','receiver','model','n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s','distance_rmse_m','signed_integral_error_m','false_stop_samples'])
  for suite in ('clean','original','low_speed','common_mode','release_diagnostic','full_original'):
   for r in data[suite]:
    fault=r.get('fault',{})
    for rec,scores in r['receivers'].items():
     for n in RATIOS:
      m=scores[n];writer.writerow([r['bag'],r['group'],suite,fault.get('kind'),fault.get('end',0)-fault.get('start',0),rec,n]+[m.get(k) for k in ('n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s')]+[legacy.metric_value(m,'distance'),m.get('signed_integral_error_m'),m.get('false_stop_samples')])

def develop(out,foundation,workers):
 f=json.loads(foundation.read_text());assert f['verdict']=='PASS','foundation not passed'
 out.mkdir(parents=True,exist_ok=False);pins=verify_sources();store=Store()
 started=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline_sha=BASELINE,baseline_tree=TREE,measured_source_sha=os.environ.get('H35_SOURCE_SHA'),stage='development',identity=enabled_identity(),source_sha256=pins,
              research_sha256={str(p.relative_to(ROOT)):sha(p) for p in HERE.rglob('*') if p.is_file() and p.suffix in ('.py','.patch','.md','.wl') and '__pycache__' not in str(p)},foundation_sha256=sha(foundation),ops=OPS,python=sys.version,numpy=np.__version__,validation_opened=False,test_opened=False)
 save(out/'started.json',started);data={k:[] for k in ('clean','original','low_speed','common_mode','release_diagnostic','full_original','access')}
 with ProcessPoolExecutor(max_workers=workers) as pool:
  for row in pool.map(worker,[(bag,out) for bag in store.plan['splits']['development']]):
   data['clean'].append(row['clean'])
   for key in data:
    if key!='clean':data[key].extend(row[key])
   save(out/'access.json',data['access'])
 save(out/'results.json',data);d=decision(data);save(out/'decision.json',d);export_csv(data,out)
 with (out/'aggregate.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['model']+list(d['summary']['v8']))
  for n,s in d['summary'].items():w.writerow([n]+list(s.values()))
 print(json.dumps(d,indent=2),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--foundation',type=Path,required=True);p.add_argument('--workers',type=int,choices=range(1,5),default=2);a=p.parse_args();develop(a.output,a.foundation,a.workers)
