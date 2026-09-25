"""Post-result telemetry, no candidate changes/retuning or new acceptance rule."""
from collections import Counter
import json
from pathlib import Path
import sys
import math
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research/H13'))
import run
from mechanism import NeutralGuard


def diagnose(output):
    if output.exists():raise FileExistsError(output)
    run.check_sources()
    total=Counter();max_residual=0.;pair_records=[]
    original=NeutralGuard.update
    interval=[0.,0.]
    def spy(g,t,u,stale,f,r,status,pred,a,cfg):
        nonlocal max_residual
        if interval[0]<=t<interval[1]:
            total['event_output_ticks']+=1
            valid=(not stale and abs(u)<=.05 and f is not None and r is not None
                   and 0<=t-f.t<=cfg.max_age_s and 0<=t-r.t<=cfg.max_age_s
                   and abs(f.t-r.t)<=cfg.pair_skew_s
                   and abs(f.value-r.value)<=cfg.disagreement_mps
                   and not any(s in ('RATE_ANOMALY','RANGE','MISSING_OR_STALE','AMBIGUOUS_PAIR','ZERO_LOCK_SUSPECT') for s in status))
            if valid and f.t>g.last_used[0] and r.t>g.last_used[1] and g.previous is not None:
                dt=(f.t+r.t)*.5-g.previous[0]
                if .05-1e-9<=dt<=.25+1e-9 and abs(u-g.previous[2])<=.05:
                    total['new_neutral_pair_with_valid_derivative']+=1
                    wheel_a=((f.value+r.value)*.5-g.previous[1])/dt
                    residual=abs((f.value+r.value)*.5-pred)
                    flags=[abs(wheel_a)>1.,abs(a)<.5,residual>.3]
                    for key,flag in zip(('wheel_acceleration_pass','model_acceleration_pass','residual_pass'),flags):
                        total[key]+=int(flag)
                    total['all_three_pass']+=int(all(flags))
                    if flags[0] and flags[1]:
                        total['both_acceleration_checks_pass']+=1
                        max_residual=max(max_residual,residual)
            else:total['not_a_new_neutral_derivative_pair']+=1
        return original(g,t,u,stale,f,r,status,pred,a,cfg)
    store=run.ev.ex.Store(ROOT/'dataset/data')
    NeutralGuard.update=spy
    try:
        for bag in store.plan['splits']['validation']:
            events,refs=store.load(bag,'validation')
            for fault,changed in run.slow_windows(events):
                interval[:]=[fault['start'],fault['end']]
                # Score wrapper observes outputs; no reference is passed to estimator.
                result=run.custom_score(changed,refs,run.models(),fault)
                pair_records.append({'bag':bag,'fault':fault,'h13':result['runtime']['candidate']['h13']})
    finally:NeutralGuard.update=original
    run.save(output,dict(kind='post-result diagnosis; frozen candidate unchanged',counters=dict(total),
                        max_residual_when_both_acceleration_checks_pass=max_residual,
                        windows=len(pair_records),windows_detail=pair_records,access=store.access))
    print(dict(total));print('max_residual_both_acceleration_pass',max_residual)

if __name__=='__main__':diagnose(Path(sys.argv[1]))
