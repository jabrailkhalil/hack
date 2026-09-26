"""Descriptive post-run analysis only; never changes candidates, data or scoring."""
from collections import defaultdict
import json,math,statistics,sys
from pathlib import Path
B='baseline_v2';C='balanced_physics';CTRL='skip_control'

def macro(rows,key,name):
    groups=defaultdict(list)
    for row in rows:
        for scores in row['receivers'].values():
            value=scores[name].get(key)
            if value is not None:groups[row['group']].append(value)
    return statistics.mean(statistics.mean(x) for x in groups.values()) if groups else None

def pct(a,b):return 100*(a/b-1) if b else None

def analyze(out):
    result=json.loads((out/'results.json').read_text()); clean=result['clean'];faults=result['stress'];extra=result['diagnostic_suites']
    def comparisons(rows,key):
        records=[]
        for row in rows:
            for receiver,scores in row['receivers'].items():
                a,b=scores[C],scores[B]
                x=a.get(key) if key!='distance' else a.get('distance_surrogate',{}).get('reanchored_span_rmse_m')
                y=b.get(key) if key!='distance' else b.get('distance_surrogate',{}).get('reanchored_span_rmse_m')
                if x is not None and y is not None:
                    records.append(dict(bag=row['bag'],group=row['group'],receiver=receiver,fault=row.get('fault'),baseline=y,candidate=x,delta=x-y,percent=pct(x,y)))
        return sorted(records,key=lambda x:x['delta'],reverse=True)
    metricpairs={k:comparisons(rows,key) for k,rows,key in [('clean',clean,'rmse'),('fault',faults,'event_rmse'),('distance',clean,'distance'),('recovery',faults,'recovery_s')]}
    bykind={}
    for kind in sorted({r['fault']['kind']+'_'+str(round(r['fault']['end']-r['fault']['start'],9)) for r in faults}):
        rows=[r for r in faults if r['fault']['kind']+'_'+str(round(r['fault']['end']-r['fault']['start'],9))==kind]
        b=macro(rows,'event_rmse',B);a=macro(rows,'event_rmse',C)
        bykind[kind]=dict(baseline=b,candidate=a,change_percent=pct(a,b) if a is not None and b is not None else None)
    phases={}
    for phase in ('transition_1s','other'):
        phases[phase]={}
        for name in (B,C,CTRL):
            groups=defaultdict(list);n=0
            for row in clean:
                for score in row.get('phase_metrics',{}).get(name,{}).values():
                    m=score[phase]
                    if m['rmse'] is not None:groups[row['group']].append(m['rmse']);n+=m['n']
            phases[phase][name]=dict(macro_rmse=statistics.mean(statistics.mean(x) for x in groups.values()) if groups else None,n=n)
    coverage=result['coverage'];c=coverage['counts']
    description=dict(role=result['role'],bags=len(clean),groups=len(set(r['group'] for r in clean)),groups_with_reference=len(set(r['group'] for r in clean if any(s[B]['n']>0 for s in r['receivers'].values()))),bag_receiver_pairs_with_reference=sum(s[B]['n']>0 for r in clean for s in r['receivers'].values()),bags_without_reference=[r['bag'] for r in clean if not any(s[B]['n']>0 for s in r['receivers'].values())],original_fault_scenarios=len(faults),fault_reference_pairs=sum(s[B].get('event_rmse') is not None for r in faults for s in r['receivers'].values()),diagnostic_fault_scenarios=len(extra),activation=coverage,skip_percent=100*c['skipped']/c['eligible'] if c['eligible'] else None,decision=result.get('decision'),skip_control=result.get('skip_control'),diagnostic_decision=result.get('diagnostic_decision'),prevalidation_verdict=result.get('prevalidation_verdict'),per_type=bykind,phase=phases,worst={k:v[:10] for k,v in metricpairs.items()},regression_counts={k:sum(r['delta']>0 for r in v) for k,v in metricpairs.items()},pairs={k:len(v) for k,v in metricpairs.items()},candidate_causal_errors=sum(r['runtime'][C]['causal_errors'] for r in clean+faults+extra),candidate_resets=sum(r['runtime'][C]['resets'] for r in clean+faults+extra),feature_off_exact_checks=len(clean)+len(faults)+len(extra))
    cost_path=out/'cost.json'
    if cost_path.exists():
        raw=json.loads(cost_path.read_text());cost={}
        for name in ('R2_guarded_v7','H13_interval_linear_v1'):
            rows=[r for r in raw['replay'] if r['model']==name]
            cost[name]=dict(wall_median_s=statistics.median(r['wall_s'] for r in rows),cpu_median_s=statistics.median(r['cpu_s'] for r in rows),outputs=rows[0]['outputs'],wall_all_s=[r['wall_s'] for r in rows],cpu_all_s=[r['cpu_s'] for r in rows])
        description['cost']=dict(bag=raw['bag'],values=cost,wall_percent=pct(cost['H13_interval_linear_v1']['wall_median_s'],cost['R2_guarded_v7']['wall_median_s']),cpu_percent=pct(cost['H13_interval_linear_v1']['cpu_median_s'],cost['R2_guarded_v7']['cpu_median_s']))
    dest=out.parent/(out.name+'-analysis.json');dest.write_text(json.dumps(description,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(dest);print(json.dumps({k:v for k,v in description.items() if k not in ('activation','worst','phase','diagnostic_decision','skip_control')},ensure_ascii=False,indent=2))
if __name__=='__main__':analyze(Path(sys.argv[1]))
