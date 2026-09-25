"""Read-only post-run audit; never invokes a loader or changes an algorithm."""
import csv,hashlib,json,math,statistics,sys
import numpy as np
from pathlib import Path
root=Path(sys.argv[1]);dest=Path(sys.argv[2]);dest.mkdir(parents=True,exist_ok=False)
data=json.loads((root/'development/results.json').read_text());decision=json.loads((root/'development/decision.json').read_text())
B,C='r2_baseline','h21_envelope'
rows={'clean':data['clean'],'original_fault':data['stress'],'diagnostic_fault':data['diagnostic_faults']}
def macro(items,name,key):
 groups={}
 for row in items:
  for scores in row['receivers'].values():
   x=scores[name].get(key)
   if x is not None:groups.setdefault(row['group'],[]).append(x)
 return float(np.mean([np.mean(v) for v in groups.values()])) if groups else None

def scalar_entries(obj,prefix=''):
 if isinstance(obj,dict):
  for k,v in obj.items():yield from scalar_entries(v,prefix+'/'+k)
 elif isinstance(obj,list):
  for k,v in enumerate(obj):yield from scalar_entries(v,prefix+'/'+str(k))
 else:yield prefix,obj
summary={};regressions=[];equal_fields=0;different=[];interval={};widths={}
for suite,items in rows.items():
 metric_summary={}
 for model in (B,C):
  metric_summary[model]={k:macro(items,model,k) for k in ('rmse','mae','bias','p95','event_rmse','recovery_s')}
  metric_summary[model].update(samples=sum(s[model]['n'] for r in items for s in r['receivers'].values()),
   false_stops=sum(s[model].get('false_stop_samples',0) for r in items for s in r['receivers'].values()),
   unrecovered=sum(s[model].get('event_rmse') is not None and s[model].get('recovery_s') is None for r in items for s in r['receivers'].values()))
 summary[suite]=dict(bags=len({r['bag'] for r in items}),groups=len({r['group'] for r in items}),rows=len(items),
  reference_pairs=sum(s[B]['rmse'] is not None for r in items for s in r['receivers'].values()),
  missing_pairs=[r['bag']+'/'+k for r in items for k,s in r['receivers'].items() if s[B]['rmse'] is None],metrics=metric_summary,
  counts={k:sum(r['h21_counts'][k] for r in items) for k in items[0]['h21_counts']} if items else {},
  all_off_checked=all(r['canonical_and_disabled_per_tick_checked'] for r in items))
 ws=[];cov={};labels={};phase={'before':{},'during':{},'after':{}}
 for row in items:
  for rec,metrics in row['receivers'].items():
   a,b=metrics[B],metrics[C]
   for k,v in scalar_entries(a):
    # Candidate-only common wheel diagnostic fields are not used for equality.
    try:
     w=b
     for path in k.split('/')[1:]:w=w[path]
    except (KeyError,TypeError):continue
    if v==w:equal_fields+=1
    else:different.append(dict(suite=suite,bag=row['bag'],receiver=rec,field=k,baseline=v,candidate=w))
   for key in ('rmse','mae','p95','event_rmse','recovery_s'):
    x,y=a.get(key),b.get(key)
    if x is not None and y is not None and y>x:
     regressions.append(dict(suite=suite,bag=row['bag'],receiver=rec,fault=row.get('fault'),metric=key,
       baseline=x,candidate=y,delta=y-x,change_percent=(100*(y/x-1) if x else None)))
  for rec,v in row['diagnostics']['interval_reference_coverage'].items():
   o=cov.setdefault(rec,dict(n=0,inside=0));o['n']+=v['n'];o['inside']+=v['inside']
  for k,n in row['diagnostics']['labels'].items():labels[k]=labels.get(k,0)+n
  for tick in row['diagnostics']['trace']:
   if tick['active'] and tick['width'] is not None:ws.append(tick['width'])
   if 'fault' in row:
    f=row['fault'];part='before' if tick['t']<f['start'] else ('during' if tick['t']<f['end'] else 'after')
    q=phase[part];q['sampled_trace_ticks']=q.get('sampled_trace_ticks',0)+1;q['sampled_active_ticks']=q.get('sampled_active_ticks',0)+int(tick['active'])
 for d in cov.values():d['fraction']=d['inside']/d['n'] if d['n'] else None
 interval[suite]=dict(coverage=cov,labels=labels,phase_sampled=phase)
 widths[suite]=dict(n_sampled=len(ws),min=min(ws) if ws else None,median=statistics.median(ws) if ws else None,max=max(ws) if ws else None,
  note='1 Hz trace subsample plus all veto ticks; not full 20 Hz width distribution')
benchmark=json.loads((root/'development/benchmark.json').read_text());timing={}
for kind,ms in benchmark['medians'].items():
 timing[kind]={k:dict(baseline=ms[B][k],candidate=ms[C][k],change_percent=100*(ms[C][k]/ms[B][k]-1)) for k in ms[B]}
train=json.loads((root/'train/results.json').read_text());ta=json.loads((root/'train/access.json').read_text());da=json.loads((root/'development/access.json').read_text())
assert all('gnss' not in t and 'imu' not in t for r in ta['access'] for t in r['topics'])
assert {r['purpose'] for r in ta['access']}=={'train'}
assert {r['purpose'] for r in da['access']}=={'development'}
assert not (root/'validation').exists(), 'This audit expects prevalidation stop; inspect actual validation separately'
result=dict(verdict=decision['verdict'],baseline=data['baseline'],measured_source=data['source_commit'],train_bags=len(train['train']),
 train_outputs=train['outputs'],train_counts={k:sum(r['h21_counts'][k] for r in train['train']) for k in train['train'][0]['h21_counts']},
 suites=summary,interval=interval,widths=widths,timing=timing,equal_fields=equal_fields,differences=different,
 regressions=regressions,train_gnss_read=False,validation_run=False,test_run=False,
 source_results_sha256=hashlib.sha256((root/'development/results.json').read_bytes()).hexdigest())
(dest/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
with (dest/'aggregates.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=['suite','model','metric','value']);w.writeheader()
 for suite,s in summary.items():
  for model,m in s['metrics'].items():
   for k,v in m.items():w.writerow(dict(suite=suite,model=model,metric=k,value=v))
print(json.dumps(result,ensure_ascii=False,indent=2)[:25000])
