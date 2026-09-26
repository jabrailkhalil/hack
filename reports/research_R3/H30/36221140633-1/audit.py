"""Read-only audit of frozen H30 evidence; no measurement payload access."""
import argparse, hashlib, importlib, json, sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--checkout',type=Path,required=True)
    ap.add_argument('--evidence',type=Path,required=True);ap.add_argument('--diagnosis',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    sys.path.insert(0,str(a.checkout/'research/R3/H30'));run=importlib.import_module('run')
    experiment=a.evidence/'experiment';start=json.loads((experiment/'STARTED.json').read_text())
    expected=json.loads((experiment/'SUMMARY.json').read_text())
    hashes=start['source_hashes'] | start['pinned_source']['sha256']
    verified={path:hashlib.sha256((a.checkout/path).read_bytes()).hexdigest()==h for path,h in hashes.items()}
    assert all(verified.values()),verified
    bag_order=run.cm.ev.ex.Store().plan['splits']['development']
    data=[json.loads((experiment/'bags'/(bag+'.json')).read_text()) for bag in bag_order]
    clean=[r['clean'] for r in data];stress=[s for r in data for s in r['original']]
    extra={name:[s for r in data for s in r[name]] for name in ('low_speed','common_mode')}
    recalc=run.decide(clean,stress,extra)
    assert all(recalc[k]==expected[k] for k in recalc),'Aggregate or decision mismatch'
    diagnosis=json.loads(a.diagnosis.read_text());db={r['bag']:r for r in diagnosis['per_bag']}
    baseline_equal={r['bag']:r['audit']['baseline_array_sha256']==db[r['bag']]['outputs_sha256'] for r in clean}
    assert all(baseline_equal.values()),baseline_equal
    all_rows=clean+stress+sum(extra.values(),[])
    for row in all_rows:
        assert row['audit']['feature_off_exact']
        for name in run.NAMES:
            assert not row['runtime'][name]['causal_errors'] and not row['runtime'][name]['resets']
    # Signed bias is not ranked as an error magnitude; preserve it in raw CSV.
    regressions=[];recovery=[]
    for suite,rows in [('clean',clean),('original',stress),*extra.items()]:
        for row in rows:
            for receiver,scores in row['receivers'].items():
                b,c=scores[run.NAMES[0]],scores[run.NAMES[1]]
                for metric in ('rmse','mae','p95','event_rmse','distance'):
                    bv=run.v6.metric_value(b,metric);cv=run.v6.metric_value(c,metric)
                    if bv is not None and cv is not None and cv>bv:
                        regressions.append(dict(suite=suite,**run.identity(row,receiver),metric=metric,
                           baseline=bv,candidate=cv,delta=cv-bv,percent=100*(cv/bv-1) if bv else None))
                bt,ct=b.get('recovery_s'),c.get('recovery_s')
                if bt!=ct:recovery.append(dict(suite=suite,**run.identity(row,receiver),baseline=bt,candidate=ct,
                           delta=ct-bt if bt is not None and ct is not None else None))
    result=dict(measured_source_sha=start['source_sha'],source_hash_checks=len(hashes),all_hashes_match=True,
       summaries_and_decisions_exact=True,independent_diagnostic_baseline_array_match=baseline_equal,
       compared_bags=len(clean),compared_replays=len(all_rows),reference_points=expected['summary']['baseline_v8']['samples'],
       no_new_replay_performed=True,validation_or_test_measurements_opened=False,
       recovery_changes=recovery,regressions=regressions)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('regressions','recovery_changes')},indent=2))
    print('recovery changes',len(recovery),'regression entries',len(regressions))
if __name__=='__main__':main()
