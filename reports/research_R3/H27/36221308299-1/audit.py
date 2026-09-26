"""Read-only descriptive audit of a finished H27 development artifact; never replays or selects."""
import argparse
import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

NAMES=('R3_v8','H27_off','H27_l020','H27_l040')
CANDIDATES=('H27_l020','H27_l040')


def write_json(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def csv_write(p,rows):
    if rows:
        with p.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main(root,out):
    out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((root/'ARTIFACT_FILES_SHA256.json').read_text())
    for name,digest in manifest.items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
    summary=json.loads((root/'development/SUMMARY.json').read_text())
    rows=[]
    for p in sorted((root/'development/bags').glob('*.json')):rows.extend(json.loads(p.read_text())['rows'])
    rows.extend(json.loads((root/'development/counterexamples.json').read_text()))
    long=[];regressions=[];group_values=defaultdict(list);activations=[]
    for row in rows:
        for name in NAMES:
            activations.append(dict(bag=row['bag'],group=row['group'],role=row['role'],suite=row['suite'],case=row['case'],model=name,**row['activation'][name]))
        for receiver,scores in row['receivers'].items():
            for name in NAMES:
                m=scores[name];b=scores['R3_v8']
                item=dict(bag=row['bag'],group=row['group'],role=row['role'],suite=row['suite'],case=row['case'],receiver=receiver,model=name,
                    rmse=m['rmse'],mae=m.get('mae'),bias=m.get('bias'),p95=m.get('p95'),n=m['n'],coverage=m['coverage'],false_stop_samples=m['false_stop_samples'],
                    event_rmse=m.get('event_rmse'),recovery_s=m.get('recovery_s'),distance_rmse=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m'))
                long.append(item)
                for metric in ['rmse','mae','bias','p95','event_rmse','distance_rmse','recovery_s']:
                    value=item[metric]
                    if value is not None:group_values[(row['suite'],row['group'],name,metric)].append(value)
                    baseline=b.get('distance_surrogate',{}).get('reanchored_span_rmse_m') if metric=='distance_rmse' else b.get(metric)
                    if name in CANDIDATES and value is not None and baseline is not None:
                        difference=abs(value)-abs(baseline) if metric=='bias' else value-baseline
                        if difference>1e-12:
                            regressions.append(dict(bag=row['bag'],group=row['group'],suite=row['suite'],case=row['case'],receiver=receiver,
                                model=name,metric=metric,baseline=baseline,candidate=value,absolute_regression=difference,
                                relative_regression=difference/abs(baseline) if abs(baseline)>1e-15 else None))
                assert m['n']==b['n'] and m['coverage']==b['coverage']
                assert m['false_stop_samples']==b['false_stop_samples']
                if name=='H27_off':assert m==b or all(m.get(k)==b.get(k) for k in ['rmse','mae','bias','p95','n','coverage','false_stop_samples','event_rmse','recovery_s','distance_surrogate'])
    groups=[dict(suite=k[0],group=k[1],model=k[2],metric=k[3],value=mean(v),receiver_cases=len(v)) for k,v in sorted(group_values.items())]
    macro=defaultdict(list)
    for r in groups:macro[(r['suite'],r['model'],r['metric'])].append(r['value'])
    macros=[dict(suite=k[0],model=k[1],metric=k[2],value=mean(v),source_groups=len(v)) for k,v in sorted(macro.items())]
    csv_write(out/'per_bag_receiver.csv',long);csv_write(out/'per_group.csv',groups);csv_write(out/'diagnostic_macro.csv',macros)
    csv_write(out/'activation.csv',activations)
    csv_write(out/'regressions.csv',sorted(regressions,key=lambda r:-r['absolute_regression']))
    table=[]
    for bag in sorted({r['bag'] for r in rows if r['suite']=='clean'}):
        item=dict(bag=bag)
        for name in NAMES:
            values=[r['rmse'] for r in long if r['bag']==bag and r['suite']=='clean' and r['model']==name and r['rmse'] is not None]
            item[name]=mean(values) if values else None
        table.append(item)
    write_json(out/'clean_bag_table.json',table)
    risk={}
    for suite in sorted({r['suite'] for r in rows}):
        sr=[r for r in rows if r['suite']==suite]
        risk[suite]={name:dict(cases=len(sr),reference_comparisons=sum(scores[name]['rmse'] is not None for row in sr for scores in row['receivers'].values()),
            false_stops=sum(scores[name]['false_stop_samples'] for row in sr for scores in row['receivers'].values()),
            unrecovered=sum(scores[name].get('event_rmse') is not None and scores[name].get('recovery_s') is None for row in sr for scores in row['receivers'].values()),
            effective_ticks=sum(row['activation'][name]['effective_ticks'] for row in sr),effective_entries=sum(row['activation'][name]['effective_entries'] for row in sr)) for name in NAMES}
    write_json(out/'suite_counts.json',risk)
    access=json.loads((root/'development/access.json').read_text())
    assert len(access)==17 and all(r['purpose']=='development' for r in access)
    for row in rows:
        for name in NAMES:assert row['runtime'][name]['causal_errors']==row['runtime'][name]['resets']==0
    audit=dict(manifest_files_verified=len(manifest),raw_score_rows=len(rows),development_bags=len(access),
        states_and_off='checked during measured replay; this audit checks saved outputs/score identities only',
        history_peak=max(a['history_peak'] for a in activations),baseline_reproduction=summary['baseline_reproduction'],
        validation_opened=False,test_evaluated=False,source_sha=(root/'MEASURED_SOURCE_SHA.txt').read_text().strip())
    write_json(out/'audit.json',audit)
    print(json.dumps(audit,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('out',type=Path);a=p.parse_args();main(a.root,a.out)
