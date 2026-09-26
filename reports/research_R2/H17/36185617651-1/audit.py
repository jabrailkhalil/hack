"""Descriptive audit of saved H17 JSON; no replay, selection or data loading."""
import argparse,csv,json,math,statistics
from collections import defaultdict,Counter
from pathlib import Path

BASE='R2_v7'
CANDIDATES=['H17_L050','H17_L100','H17_L200']

def average(values):return sum(values)/len(values) if values else None

def macro(rows,name,key):
    groups=defaultdict(list)
    for row in rows:
        for receiver,scores in row['receivers'].items():
            m=scores[name]
            value=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m') if key=='distance' else m.get(key)
            if value is not None:groups[row['group']].append(value)
    return average([average(v) for v in groups.values()])

def delta(c,b):return None if b in (None,0) or c is None else 100*(c/b-1)

def audit(root,out,stage="development"):
    global CANDIDATES
    r=json.loads((root/stage/'results.json').read_text());decision=json.loads((root/stage/'decision.json').read_text())
    CANDIDATES=[n for n in r['models'] if n.startswith('H17_')]
    names=[BASE,*CANDIDATES];clean=r['clean'];stress=r['stress'];extra=r['extra']
    result={'baseline':r['baseline'],'measured_source':(root/'MEASURED_SOURCE_SHA.txt').read_text().strip(),
        'counts':{'clean_bags':len(clean),'groups':len({x['group'] for x in clean}),
                  'reference_groups':len({x['group'] for x in clean if any(m[BASE]['n'] for m in x['receivers'].values())}),
                  'clean_reference_pairs':sum(m[BASE]['n']>0 for x in clean for m in x['receivers'].values()),
                  'original_scenarios':len(stress),'extra_scenarios':len(extra),
                  'original_reference_pairs':sum(m[BASE]['event_rmse'] is not None for x in stress for m in x['receivers'].values()),
                  'extra_reference_pairs':sum(m[BASE]['event_rmse'] is not None for x in extra for m in x['receivers'].values())},
        'missing_reference':[x['bag']+'/'+recv for x in clean for recv,m in x['receivers'].items() if m[BASE]['rmse'] is None],
        'aggregates':r['aggregates'],'decision':decision,'per_bag':[],
        'regressions':{},'coverage':{},'phase':{},'suites':{},'fault_state_deltas':{},'local_recovery_deltas':{}}
    for row in clean:
        values={n:average([m[n]['rmse'] for m in row['receivers'].values() if m[n]['rmse'] is not None]) for n in names}
        result['per_bag'].append({'bag':row['bag'],'group':row['group'],'rmse':values,'change_percent':{n:delta(values[n],values[BASE]) for n in CANDIDATES}})
    for n in names:
        counters=Counter()
        for row in clean:counters.update(row['diagnostics'][n]['counts'])
        result['coverage'][n]={'counters':dict(counters),'changed_selected_duration_s':.05*counters.get('changed_selected_ticks',0),
          'history_peak':max(x['diagnostics'][n]['history_peak'] for x in clean),
          'causal_errors':sum(x['runtime'][n]['causal_errors'] for x in clean+stress+extra),
          'resets':sum(x['runtime'][n]['resets'] for x in clean+stress+extra),
          'mode_counts':dict(sum((Counter(x['runtime'][n]['mode_counts']) for x in clean),Counter()))}
        result['phase'][n]={}
        for mode in (-1,0,1):
            groups=defaultdict(lambda:defaultdict(list));counts=0
            for row in clean:
                for key,m in row['diagnostics'][n]['phase'].items():
                    if key.endswith('/'+str(mode)) and m['rmse'] is not None:
                        counts+=m['n']
                        for metric in ('rmse','mae','bias','p95'):groups[row['group']][metric].append(m[metric])
            result['phase'][n][str(mode)]={metric:average([average(g[metric]) for g in groups.values()]) for metric in ('rmse','mae','bias','p95')}
            result['phase'][n][str(mode)].update(n=counts,groups=len(groups))
    for suite,rows in [('original',stress),('extra',extra)]:
        types=defaultdict(list)
        for row in rows:
            f=row['fault'];key=f['kind']+'_'+str(round(f['end']-f['start'],3))+'_'+f.get('diagnostic','original')
            types[key].append(row)
        result['suites'][suite]={k:{n:{m:macro(v,n,m) for m in ('rmse','mae','bias','p95','event_rmse','recovery_s')} for n in names} for k,v in types.items()}
    for n in CANDIDATES:
        reg=[];rec=[];states=[]
        for suite,rows in [('clean',clean),('original',stress),('extra',extra)]:
            for row in rows:
                for receiver,m in row['receivers'].items():
                    b,c=m[BASE],m[n]
                    for metric in ('rmse','event_rmse','mae','p95','bias','distance'):
                        bv=b.get('distance_surrogate',{}).get('reanchored_span_rmse_m') if metric=='distance' else b.get(metric)
                        cv=c.get('distance_surrogate',{}).get('reanchored_span_rmse_m') if metric=='distance' else c.get(metric)
                        if bv is None or cv is None:continue
                        abs_delta=abs(cv)-abs(bv) if metric=='bias' else cv-bv
                        if abs_delta>1e-12:reg.append(dict(suite=suite,bag=row['bag'],receiver=receiver,fault=row.get('fault'),metric=metric,baseline=bv,candidate=cv,absolute_worsening=abs_delta,percent=delta(abs(cv),abs(bv)) if metric=='bias' else delta(cv,bv)))
                    if suite!='clean' and b.get('event_rmse') is not None:
                        a,z=b.get('recovery_s'),c.get('recovery_s')
                        if a!=z:rec.append(dict(suite=suite,bag=row['bag'],receiver=receiver,fault=row['fault'],baseline=a,candidate=z,delta_s=z-a if a is not None and z is not None else None))
                if suite!='clean':
                    f=row['fault'];pairs=[]
                    for model in (BASE,n):
                        vals=[x for x in row['diagnostics'][model]['traces'] if x['t']<f['start']]
                        pairs.append(vals[-1] if vals else None)
                    if all(x is not None for x in pairs):
                        a,b=pairs;states.append(dict(suite=suite,bag=row['bag'],fault=f,t=a['t'],
                            baseline_disturbance=a['disturbance'],candidate_disturbance=b['disturbance'],
                            delta_disturbance=b['disturbance']-a['disturbance'],baseline_v=a['published_v'],candidate_v=b['published_v'],
                            baseline_drive_a=a['drive_a'],candidate_drive_a=b['drive_a'],u=b['u'],delayed_u=b['u_delayed']))
        result['regressions'][n]=sorted(reg,key=lambda x:x['absolute_worsening'],reverse=True)
        result['local_recovery_deltas'][n]=rec
        result['fault_state_deltas'][n]=sorted(states,key=lambda x:abs(x['delta_disturbance']),reverse=True)
    if (root/'cost/cost.json').exists():
        cost=json.loads((root/'cost/cost.json').read_text());result['cost']={}
        for n in CANDIDATES:
            rows=[x for x in cost['results'] if x['candidate']==n];summ={}
            for metric in ['replay_cpu_s','replay_wall_s','step_cpu_s','step_wall_s']:
                pairs={}
                for x in rows:pairs.setdefault((x['repeat'],x['order']),{})[x['label']]=x[metric]
                ratios=[100*(v['B']/v['A']-1) for v in pairs.values()]
                summ[metric]={'baseline_median':statistics.median(x[metric] for x in rows if x['label']=='A'),
                    'candidate_median':statistics.median(x[metric] for x in rows if x['label']=='B'),
                    'paired_change_median_percent':statistics.median(ratios),'paired_change_min_percent':min(ratios),'paired_change_max_percent':max(ratios)}
            summ['post_warmup_steps']=sorted({x['post_warmup_steps'] for x in rows});summ['outputs']=sorted({x['outputs'] for x in rows})
            summ['rss_peak_bytes']=max(x['process_peak_rss_bytes'] for x in rows)
            summ['same_algorithm_repeat_output_hashes']={label:len({x['output_sha256'] for x in rows if x['label']==label}) for label in ['A','B']}
            result['cost'][n]=summ
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ['counts','aggregates']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('evidence',type=Path);p.add_argument('output',type=Path);p.add_argument('--stage',choices=['development','validation'],default='development');a=p.parse_args();audit(a.evidence,a.output,a.stage)
