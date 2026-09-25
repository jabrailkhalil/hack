"""Acceptance of a safety coverage extension without replacing original metrics."""
import argparse
import json
from pathlib import Path


def verify(original, extension):
    assert len(original['clean'])==19 and len(original['stress'])==76
    assert len(extension['stress'])==38
    for row in original['clean']+original['stress']:
        for scores in row['receivers'].values():
            for baseline,candidate in [('main_v4','v4_zero_lock'),('main','v5_zero_lock')]:
                for key,value in scores[baseline].items():
                    assert scores[candidate][key]==value,(row['bag'],candidate,key)
    result={}
    for baseline,candidate in [('main_v4','v4_zero_lock'),('main_v5','v5_zero_lock')]:
        a=extension['summary'][candidate];b=extension['summary'][baseline]
        gain=1-a['event_group_macro_rmse']/b['event_group_macro_rmse']
        assert gain>=.05 and a['false_stop_samples']<b['false_stop_samples']
        for row in extension['stress']:
            assert row['counts'][candidate]['causal_errors']==0
            for scores in row['receivers'].values():
                a0=scores[candidate];b0=scores[baseline]
                assert a0['n']==b0['n'] and a0['coverage']==b0['coverage']
                assert a0.get('false_stop_samples',0)<=b0.get('false_stop_samples',0)
                if b0.get('recovery_s') is not None:assert a0.get('recovery_s') is not None
        result[candidate]=dict(low_speed_event_gain=gain,baseline=baseline,original_metrics_unchanged=True,**a)
    assert not original['test_evaluated'] and not extension['test_evaluated']
    return dict(eligible=True,scope='separate low-speed fault coverage extension; original suite unchanged',profiles=result)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--original',type=Path,required=True);p.add_argument('--extension',type=Path,required=True)
    args=p.parse_args();print(json.dumps(verify(json.loads(args.original.read_text()),json.loads(args.extension.read_text())),indent=2))
