"""Post-run independent audit; does not re-open bags or re-fit a candidate."""
import json, math, statistics, hashlib
from pathlib import Path
import numpy as np

import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--evidence',type=Path,required=True,help='Extracted original Actions artifact directory')
ROOT=parser.parse_args().evidence
def load(p): return json.loads((ROOT/p).read_text())
s=load('train/SUMMARY.json'); b=load('train/per_bag.json'); a=np.load(ROOT/'train/selected_pairs.npz',allow_pickle=False)
manifest=load('train/pairs_manifest.json')
assert hashlib.sha256((ROOT/'train/selected_pairs.npz').read_bytes()).hexdigest()==manifest['sha256']
access=load('train/access.json')
assert len(access)==64 and len({x['bag'] for x in access})==64
assert all(x['purpose']=='train' and set(x['topics'])=={'/vehicle/driver_position_cmd','/vehicle/front_bogie_velocity','/vehicle/rear_bogie_velocity'} for x in access)
assert all(x['exact_baseline_reproduction'] and x['runtime']['causal_errors']==0 and x['runtime']['resets']==0 for x in b)
vals={}
for bag in a.files:
    x=a[bag]
    assert np.isfinite(x).all()
    if len(x):
        assert np.all((np.abs(x[:,7:9])>=2)&(np.abs(x[:,7:9])<=30))
        assert np.all(x[:,7]*x[:,8]>0) and np.all(x[:,5]<=.025)
        assert np.allclose(.5*np.log(x[:,8]/x[:,7]),x[:,1],rtol=0,atol=1e-15)
for group in s['groups']:
    values=[statistics.median(a[bag][:,1]) for bag in group['bags']]
    value=statistics.median(values)
    assert value==group['delta']
    vals[group['group']]=value
fit=[vals[g] for g in s['roles'] if s['roles'][g]=='fit' and g in vals]
if fit: assert statistics.median(fit)==s['delta_raw']
result={'raw_pair_hash_verified':True,'independent_group_and_fit_medians_exact':True,
        'all_access_train_vehicle_only':True,'all_official_baseline_outputs_and_counters_equal':True,
        'all_64_bags_completed':True,'all_raw_ratios_and_recorded_selection_bounds_verified':True,
        'recorded_raw_pair_columns':manifest['columns'],
        'audit_scope':'Post-hoc audit of existing artifacts only; no new bag I/O, parameters, candidate, development or validation.'}
(ROOT/'AUDIT.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(s,indent=2))
print('AUDIT_PASS')
