"""Selected unchanged functions from jabrailkhalil/hack @ e3b0c9c.

Function bodies are transcribed from tools/finalization/evaluate.py and
research_v3/experiment.py. Imports are reduced to permit offline execution.
This is a NEW audit; immutable upstream FREEZE/final-test gates are not altered.
The Observer name is bound to a selected factory by the standalone runner.
"""
from collections import Counter
import math
import numpy as np
from reserve_odometry.core import Observer, Sample
from reserve_odometry.timeline import Timeline


def replay(events,config,ops,fault=None):
    timeline=Timeline(Observer(config),rate_hz=ops['rate_hz'],delay_s=ops['alignment_delay_s'])
    output=[];modes=Counter();causal_errors=0
    for t,ch,value in events:
        ch=int(ch)
        if fault and fault['start']<=t<fault['end']:
            if fault['kind']=='dropout' and ch in (1,2): continue
            if fault['kind']=='lock' and ch in (1,2): value=0.
            if fault['kind']=='bias' and ch==1: value+=5.
        timeline.ingest(ch,Sample(float(t),float(value)))
        for e,held in timeline.advance():
            if e.mode=='WAITING_FOR_INITIALIZATION':continue
            modes[e.mode]+=1
            causal_errors+=sum(s is not None and s.t>e.t+1e-9 for s in held)
            wheels=[s.value if s is not None and 0<=e.t-s.t<=config.max_age_s else np.nan for s in held[1:]]
            output.append((e.t,e.v,e.s,wheels[0],sum(wheels)/2,e.mode=='STOPPED'))
    a=np.asarray(output,float).reshape(-1,6)
    if len(a) and (not np.all(np.isfinite(a[:,:3])) or not np.all(np.diff(a[:,0])>0)):
        raise AssertionError('Nonfinite/nonmonotone inference')
    return a,dict(resets=timeline.resets,dropped=timeline.dropped,catchups=timeline.catchup_events,
        causal_errors=causal_errors,mode_counts=dict(modes))


def distance_surrogate(prediction,target):
    """Scalar distance vs GNSS-speed integral, NOT xyz/ENU position accuracy."""
    t,s=prediction[:,0],prediction[:,2];valid=np.isfinite(target)
    result=dict(definition='s versus integral matched horizontal GNSS speed; NOT xyz',full_span_terminal_error_m=None,
        full_span_reference_distance_m=None,full_span_terminal_drift_percent=None,continuous_spans=0,reanchored_span_rmse_m=None)
    if len(t)<2:return result
    edge=valid[:-1]&valid[1:]&(np.diff(t)<=.051)
    starts=np.flatnonzero(edge & np.r_[True,~edge[:-1]])
    ends=np.flatnonzero(edge & np.r_[~edge[1:],True])+1
    squares=0.;count=0;longest=None
    for begin,end in zip(starts,ends):
        if t[end]-t[begin]<1.:continue
        ts=t[begin:end+1];v=target[begin:end+1]
        reference_s=np.r_[0.,np.cumsum((v[1:]+v[:-1])*.5*np.diff(ts))]
        error=s[begin:end+1]-s[begin]-reference_s;squares+=float(np.sum(error**2));count+=len(error)
        result['continuous_spans']+=1
        span=dict(start_s=float(t[begin]),duration_s=float(t[end]-t[begin]),reference_distance_m=float(reference_s[-1]),terminal_error_m=float(error[-1]))
        if longest is None or span['duration_s']>longest['duration_s']:longest=span
    result['longest_reference_span']=longest
    if count:result['reanchored_span_rmse_m']=math.sqrt(squares/count)
    if np.all(edge):
        distance=float(np.sum((target[1:]+target[:-1])*.5*np.diff(t)));error=float(s[-1]-s[0]-distance)
        result.update(full_span_terminal_error_m=error,full_span_reference_distance_m=distance,
            full_span_terminal_drift_percent=100*error/distance if distance>1. else None)
    return result


def match(reference,t):
    if not reference:return np.full(len(t),np.nan)
    ref=np.array(sorted(dict(reference).items()));j=np.clip(np.searchsorted(ref[:,0],t),0,len(ref)-1);prev=np.maximum(j-1,0)
    j=np.where(abs(ref[prev,0]-t)<abs(ref[j,0]-t),prev,j)
    return np.where(abs(ref[j,0]-t)<=.05,ref[j,1],np.nan)


def metrics(t,estimate,reference,mask):
    mask=mask & np.isfinite(estimate) & np.isfinite(reference);e=estimate[mask]-reference[mask]
    if not len(e):return dict(n=0,coverage=0.,rmse=None)
    edge=mask[1:] & mask[:-1] & (np.diff(t)<.051);er=estimate-reference
    return dict(n=len(e),coverage=float(mask.mean()),rmse=float(np.sqrt(np.mean(e*e))),mae=float(np.mean(abs(e))),
        bias=float(np.mean(e)),p95=float(np.quantile(abs(e),.95)),
        integrated_error_m_not_xyz=float(np.sum(((er[1:]+er[:-1])/2)[edge]*np.diff(t)[edge])))


def grid_channels(events,dt=.1):
    series=[]
    for ch in range(3):
        a=events[events[:,1]==ch][:,[0,2]];a=a[np.argsort(a[:,0],kind='stable')]
        _,i=np.unique(a[:,0],return_index=True);series.append(a[i])
    if any(len(a)<2 for a in series):return None
    t=np.arange(0,events[:,0].max()+1e-8,dt);values=[];valid=np.ones(len(t),bool)
    for ch,a in enumerate(series):
        j=np.searchsorted(a[:,0],t,side='right')-1;ok=(j>=0);j=np.maximum(j,0)
        ok &= (t-a[j,0] <= (.5 if ch==0 else .25)) & np.isfinite(a[j,1])
        values.append(np.where(ok,a[j,1],0));valid &= ok
    return t,*values,valid
