"""Read-only post-processing of the completed train diagnostic; no refitting."""
import argparse
import csv
import json
from pathlib import Path
from collections import defaultdict
from support import np, save, sha


def export_csv(path, rows):
    with path.open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def describe(a):
    if not len(a):return dict(n=0,abs_residual_quantiles=None,nu4_R_ratio=None,nu8_R_ratio=None)
    return dict(n=len(a),abs_residual_quantiles=dict(zip(('50','95','99','99.9','100'),map(float,np.quantile(abs(a[:,1]),[.5,.95,.99,.999,1.])))),
      nu4_R_ratio=dict(zip(('min','median','max'),map(float,np.quantile(a[:,10]/a[:,9],[0,.5,1.])))),
      nu8_R_ratio=dict(zip(('min','median','max'),map(float,np.quantile(a[:,11]/a[:,9],[0,.5,1.])))))


def run(source, output):
    output.mkdir(parents=True,exist_ok=False)
    d=json.loads((source/'foundation.json').read_text());rows=[];groups=defaultdict(list);all_arrays=[]
    for b in d['per_bag']:
        with np.load(source/(b['bag']+'.npz')) as z:a=z['innovations']
        tail=abs(a[:,1])>3*np.sqrt(a[:,3]);fresh=a[:,4]<=.1+1e-12;stable=a[:,6]>=.5;mask=tail&fresh&stable
        row=dict(bag=b['bag'],group=b['group'],accepted_updates=len(a),raw_confidence_tails=int(tail.sum()),
          fresh_tails=int((tail&fresh).sum()),eligible_cases=int(mask.sum()),
          nu4_change_ge1pct=int(np.sum(mask&(abs(a[:,10]/a[:,9]-1)>=.01))),
          nu8_change_ge1pct=int(np.sum(mask&(abs(a[:,11]/a[:,9]-1)>=.01))),
          nu4_R_lower_ge1pct=int(np.sum(mask&(a[:,10]/a[:,9]<=.99))),
          nu4_R_higher_ge1pct=int(np.sum(mask&(a[:,10]/a[:,9]>=1.01))),
          nu8_R_lower_ge1pct=int(np.sum(mask&(a[:,11]/a[:,9]<=.99))),
          nu8_R_higher_ge1pct=int(np.sum(mask&(a[:,11]/a[:,9]>=1.01))))
        rows.append(row);groups[b['group']].append(row);all_arrays.append(a)
    a=np.concatenate(all_arrays);tail=abs(a[:,1])>3*np.sqrt(a[:,3]);fresh=a[:,4]<=.1+1e-12;stable=a[:,6]>=.5;mask=tail&fresh&stable
    assert int(mask.sum())==d['foundation_subhard_cases']
    for nu,col in [(4,10),(8,11)]:assert int(np.sum(mask&(abs(a[:,col]/a[:,9]-1)>=.01)))==d['weight_changes_on_foundation'][str(nu)]
    grouped=[]
    for g,items in sorted(groups.items()):
        sums={k:sum(r[k] for r in items) for k in rows[0] if k not in ('bag','group')}
        grouped.append(dict(group=g,bags=len(items),**sums))
    export_csv(output/'train_per_bag.csv',rows);export_csv(output/'train_per_group.csv',grouped)
    strata=[]
    for item in d['strata']:
        row={k:v for k,v in item.items() if k!='abs_residual_quantiles'}
        for q,v in item['abs_residual_quantiles'].items():row['abs_residual_q'+q]=v
        strata.append(row)
    export_csv(output/'train_strata.csv',strata)
    retained=a[mask];counts=dict(all_accepted_valid_command=len(a),confidence_tails=int(tail.sum()),fresh_tails=int((tail&fresh).sum()),
      fresh_command_stable_updates=int((fresh&stable).sum()),foundation_cases=int(mask.sum()),
      source_groups=len(groups),groups_with_foundation=len(d['foundation_groups']),
      nu4_R_lower_ge1pct=sum(r['nu4_R_lower_ge1pct'] for r in rows),nu4_R_higher_ge1pct=sum(r['nu4_R_higher_ge1pct'] for r in rows),
      nu8_R_lower_ge1pct=sum(r['nu8_R_lower_ge1pct'] for r in rows),nu8_R_higher_ge1pct=sum(r['nu8_R_higher_ge1pct'] for r in rows))
    result=dict(original_foundation_sha256=sha(source/'foundation.json'),sufficient=d['sufficient'],counts=counts,
       all=describe(a),fresh_stable=describe(a[fresh&stable]),foundation=describe(retained),
       age_bins_s=[0,.025,.05,.1,.25],abs_model_acceleration_bins_mps2=[0,.1,.5,3],mode_encoding={'-1':'braking','0':'neutral','1':'traction'},
       interpretation='Post-hoc descriptive breakdown using the SAME registered masks, not new thresholds; R lower than legacy means more weight, not necessarily better accuracy.',
       candidate_accuracy=None,validation_opened=False,test_opened=False)
    save(output/'TRAIN_AUDIT.json',result)
    export_csv(output/'foundation_cases.csv',[dict(zip(d['columns'],map(float,r))) for r in retained])
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.source,a.output)
