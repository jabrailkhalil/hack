"""R3-H26 train-only foundation; passive instrumentation, no candidate fitting.

Run from an exact pinned baseline plus research files. The immutable manifest is
checked before SQL IO. No validation/test loader exists in this script.
"""
from collections import Counter, deque
from dataclasses import asdict, fields
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'src/reserve_odometry'), str(ROOT / 'tools/finalization')]
import evaluate as ev
import numpy as np
from reserve_odometry.core import Config, clip
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.timeline import Timeline
from reserve_odometry.core import Sample

BASELINE = 'e3b0c9c039d2953fbfcda51231263d38ef9f1024'
PRECHECK_COMMIT = '92e8271945f06f8ff332eeb41816cb8d6a8332dc'
HERE = Path(__file__).resolve().parent
COLUMNS = ['t', 'pair_t', 'segment', 'raw', 'age_adjusted', 'u', 'v_prior',
           'a_model', 'drive_lag', 'd_old', 'prior_accel_mismatch', 'age',
           'skew', 'steady', 'tight', 'published_v', 'inner_v', 'gain']
IDX = {n: i for i, n in enumerate(COLUMNS)}


def save(path, data):
    ev.save(path, data)


def profile():
    text = (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text()
    vals = {}
    for line in text.splitlines():
        k, sep, v = line.strip().partition(':')
        if sep and v.strip() and not k.startswith('#'):
            try: vals[k] = float(v.strip())
            except ValueError: pass
    model = {k[6:]: v for k, v in vals.items() if k.startswith('model.')}
    if set(model) != {f.name for f in fields(Config)}:
        raise ValueError('Every model field must be specified by champion_v8.yaml')
    ro = {k[8:]: v for k, v in vals.items() if k.startswith('readout.')}
    assert ro == dict(gain=1., holdoff_s=.5)
    assert (vals['rate_hz'], vals['alignment_delay_s']) == (20., 0.)
    assert model['common_mode_quarantine_s'] == 1.5
    assert model['adaptation_tau_s'] == .5 and model['wheel_time_compensation'] == 0.
    return Config(**model), ReadoutConfig(**ro)


def integrity():
    manifest = json.loads((HERE/'manifest.json').read_text())
    assert manifest['baseline'] == BASELINE
    for name, expected in manifest['sha256'].items():
        if ev.sha(ROOT/name) != expected:
            raise ValueError('Pinned source changed: '+name)
    return dict(passed=True, **manifest)


class Probe(GuardedReadoutObserver):
    """Passive diagnostic; no writes to any inherited runtime field."""
    def __init__(self, config=None, *, readout=None, check_state=False):
        self.check_state = check_state
        self.reference = None
        self.probe = None
        super().__init__(config, readout=readout)
        if check_state:
            self.reference = GuardedReadoutObserver(config, readout=readout)

    def reset(self, **kwargs):
        super().reset(**kwargs)
        self.probe = None
        if self.reference is not None:
            self.reference.reset(**kwargs)

    def step(self, t, command=None, front=None, rear=None):
        old_t, old_v, old_d, old_pv = self.t, self.v, self.disturbance, self.pv
        estimate = super().step(t, command, front, rear)
        if self.reference is not None:
            ref = self.reference.step(t, command, front, rear)
            assert estimate == ref, ('published_state', t)
            for key, value in vars(self.reference).items():
                assert getattr(self, key) == value, ('internal_state', key, t)
        self.probe = None
        if old_t is None or estimate.mode != 'FUSED' or estimate.command_stale:
            return estimate
        dt = t-old_t
        u = clip(command.value, -1, 1)
        a = clip(self.drive_a-self.resistance(old_v)+old_d,
                 -self.c.max_accel_mps2, self.c.max_accel_mps2)
        predicted = clip(old_v+dt*a, -self.c.max_speed_mps, self.c.max_speed_mps)
        if u <= self.c.command_deadband and old_v*predicted < 0:
            predicted = 0.
        z = .5*(front.value+rear.value)
        tz = .5*(front.t+rear.t)
        age = t-tz
        residual = z-predicted
        r = self.c.wheel_sigma_mps**2*max(1., abs(residual)/(3*self.c.wheel_sigma_mps))
        p = old_pv+self.c.process_noise_v*dt
        k = p/(p+r)
        assert abs(self.v-(predicted+k*residual)) <= 1e-12
        self.probe = dict(t=t, pair_t=tz, z=z, raw=residual,
                          age_adjusted=residual+a*age, u=u, v_prior=predicted,
                          a_model=a, drive_lag=self.drive_target(u,old_v)-self.drive_a,
                          d_old=old_d, age=age, skew=abs(front.t-rear.t),
                          published_v=estimate.v, inner_v=self.v, gain=k,
                          pair_delta=abs(front.value-rear.value))
        return estimate


def trace(events, *, check_state=False):
    config, ro = profile()
    observer = Probe(config, readout=ro, check_state=check_state)
    tl = Timeline(observer, rate_hz=20., delay_s=0.)
    history = deque(maxlen=64)
    good_since, previous, previous_accel = None, None, None
    segment, output_count = 0, 0
    rows, counters = [], Counter()
    for stamp, channel, value in events:
        tl.ingest(int(channel), Sample(float(stamp), float(value)))
        for e, held in tl.advance():
            output_count += e.mode != 'WAITING_FOR_INITIALIZATION'
            counters[e.mode] += 1
            command, front, rear = held
            c = observer.c
            healthy = (not e.command_stale and
                       all(s is not None and observer._valid(s,e.t,c.max_age_s) for s in (front,rear)) and
                       abs(front.value-rear.value)<=.15 and
                       abs(front.t-rear.t)<=c.pair_skew_s and
                       all(s in ('ACCEPTED','DUPLICATE_OR_OLD') for s in (e.front_status,e.rear_status)) and
                       e.mode not in ('STOPPED','REACQUIRING','INITIALIZED','WAITING_FOR_INITIALIZATION'))
            if not healthy:
                good_since = None
                previous, previous_accel = None, None
                segment += 1
                history.clear()
            else:
                if good_since is None: good_since=e.t
                history.append((e.t,command.value))
                while history and history[0][0] < e.t-2.-1e-9: history.popleft()
            d = observer.probe
            if d is None: continue
            counters['fused_nonstale'] += 1
            if not healthy or abs(d['z'])<=.5 or abs(d['raw'])>3*c.wheel_sigma_mps:
                previous, previous_accel = None, None
                segment += 1
                continue
            if previous is not None and not 0 < d['pair_t']-previous['pair_t'] <= c.max_age_s+1e-9:
                previous, previous_accel = None, None
                segment += 1
            mismatch = previous_accel-d['a_model'] if previous_accel is not None else float('nan')
            span = max(v for _,v in history)-min(v for _,v in history) if history else math.inf
            steady = (good_since is not None and e.t-good_since>=2.-1e-9 and
                      history and e.t-history[0][0]>=1.95-1e-9 and
                      span<=.02 and abs(d['drive_lag'])<=.1)
            tight = bool(steady and math.isfinite(mismatch) and abs(mismatch)<=.2)
            row = dict(d,segment=segment,prior_accel_mismatch=mismatch,steady=float(bool(steady)),tight=float(tight))
            rows.append([row[k] for k in COLUMNS])
            previous_accel = ((d['z']-previous['z'])/(d['pair_t']-previous['pair_t'])) if previous else None
            previous=d
    a=np.asarray(rows,float).reshape(-1,len(COLUMNS))
    counters.update(outputs=output_count,trusted=len(a),steady=int(np.sum(a[:,IDX['steady']])),tight=int(np.sum(a[:,IDX['tight']])))
    return a, dict(counters), dict(resets=tl.resets,dropped=tl.dropped,catchups=tl.catchup_events)


def features(a):
    return np.column_stack((np.ones(len(a)),a[:,IDX['u']],a[:,IDX['v_prior']]/40.,
        a[:,IDX['a_model']]/3.,a[:,IDX['drive_lag']]/3.,a[:,IDX['d_old']]/.6,
        a[:,IDX['prior_accel_mismatch']]/3.,a[:,IDX['age']]/.25,a[:,IDX['skew']]/.1))


def statistics(items, variant, subset, coef):
    xs,ys,values=[],[],[]
    for a in items:
        if not len(a): continue
        y=a[:,IDX['raw' if variant=='raw' else 'age_adjusted']].copy()
        if variant=='controlled': y-=features(a)@coef
        mask=np.isfinite(y)
        if subset!='trusted': mask &= a[:,IDX[subset]]>0
        dt=np.diff(a[:,IDX['pair_t']])
        edge=(mask[1:] & mask[:-1] & (a[1:,IDX['segment']]==a[:-1,IDX['segment']]) &
              (dt>=.08-1e-9) & (dt<=.12+1e-9))
        xs.extend(y[:-1][edge]);ys.extend(y[1:][edge]); values.extend(y[mask])
    x=np.asarray(xs);y=np.asarray(ys);values=np.asarray(values)
    rho=None
    if len(x)>1 and np.std(x)>1e-12 and np.std(y)>1e-12:
        rho=float(np.corrcoef(x,y)[0,1])
    return dict(n=int(len(values)),pairs=int(len(x)),lag1_correlation=rho,
                rms=float(np.sqrt(np.mean(values**2))) if len(values) else None,
                mean=float(np.mean(values)) if len(values) else None,
                centered_std=float(np.std(values)) if len(values) else None)


def partition(records):
    groups=sorted({r['group'] for r in records if r['split']=='train'},
                  key=lambda g: hashlib.sha256(('R3-H26:'+g).encode()).hexdigest())
    check=groups[::4]
    return dict(fitting=[g for g in groups if g not in check],check=check)


def analyze(traces, records):
    split=partition(records)
    grouped={g:[] for g in split['fitting']+split['check']}
    by_name={r['bag']:r for r in records}
    for bag,a in traces.items(): grouped[by_name[bag]['group']].append(a)
    lhs=np.zeros((9,9));rhs=np.zeros(9); fit_groups=[];fit_points=0
    for g in split['fitting']:
        a=np.concatenate(grouped[g],axis=0) if grouped[g] else np.empty((0,len(COLUMNS)))
        X=features(a);y=a[:,IDX['age_adjusted']]
        ok=np.all(np.isfinite(X),axis=1)&np.isfinite(y)
        X=X[ok];y=y[ok]
        if not len(y):continue
        lhs+=X.T@X/len(y);rhs+=X.T@y/len(y)
        fit_groups.append(g);fit_points+=len(y)
    if not fit_groups:raise ValueError('No eligible fitting data')
    lhs/=len(fit_groups);rhs/=len(fit_groups)
    lhs+=np.diag([0.]+[1e-3]*8)
    coef=np.linalg.solve(lhs,rhs)
    pergroup=[];perbag=[]
    for g,items in grouped.items():
        for variant in ('raw','age_adjusted','controlled'):
            for subset in ('trusted','steady','tight'):
                pergroup.append(dict(group=g,role='check' if g in split['check'] else 'fitting',
                    variant=variant,subset=subset,**statistics(items,variant,subset,coef)))
    for bag,a in traces.items():
        for variant in ('raw','age_adjusted','controlled'):
            for subset in ('trusted','steady','tight'):
                perbag.append(dict(bag=bag,group=by_name[bag]['group'],variant=variant,subset=subset,
                    **statistics([a],variant,subset,coef)))
    rows=[r for r in pergroup if r['role']=='check' and r['variant']=='controlled' and
          r['subset']=='tight' and r['pairs']>=200 and r['lag1_correlation'] is not None]
    enough=len(rows)>=3 and sum(r['pairs'] for r in rows)>=1000
    supporting=[r for r in rows if r['lag1_correlation']>=.10 and r['rms']>=.01]
    median=float(np.median([r['lag1_correlation'] for r in rows])) if rows else None
    age=[r['lag1_correlation'] for r in pergroup if r['role']=='check' and r['variant']=='age_adjusted'
         and r['subset']=='steady' and r['pairs']>=200 and r['lag1_correlation'] is not None]
    before=float(np.median(age)) if age else None
    fit=[r['lag1_correlation'] for r in pergroup if r['role']=='fitting' and r['variant']=='controlled'
         and r['subset']=='tight' and r['pairs']>=200 and r['lag1_correlation'] is not None]
    fitmedian=float(np.median(fit)) if fit else None
    reasons=[]
    if not enough: reasons.append('insufficient_controlled_group_coverage')
    if not rows or len(supporting)<math.ceil(2*len(rows)/3) or median<.10:
        reasons.append('no_stable_positive_controlled_serial_correlation')
    if median is None or before is None or median<.5*max(0.,before):
        reasons.append('correlation_not_retained_after_dynamics_control')
    if median is None or fitmedian is None or median*fitmedian<0:
        reasons.append('fit_check_correlation_sign_instability')
    result=dict(baseline=BASELINE,precheck_commit=PRECHECK_COMMIT,split=split,
        nuisance=dict(kind='group-balanced fixed ridge; not runtime fit',coefficient=coef.tolist(),
                      fitting_groups=fit_groups,fitting_points=fit_points,ridge=1e-3),
        foundation_passed=not reasons,scientific_verdict='PROCEED_TO_PLAN' if not reasons else 'INCONCLUSIVE',
        reasons=reasons,qualifying_check_groups=len(rows),qualifying_check_pairs=sum(r['pairs'] for r in rows),
        supporting_check_groups=len(supporting),controlled_check_median_rho1=median,
        age_adjusted_steady_check_median_rho1=before,controlled_fitting_median_rho1=fitmedian,
        actual_candidate_interventions=0,ar1_objective_calls=0,validation_accessed=False,test_accessed=False)
    return result,pergroup,perbag


def write_csv(path,rows):
    if not rows:return
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,default=ROOT/'dataset/data')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();guard=integrity();args.output.mkdir(parents=True,exist_ok=False)
    save(args.output/'started.json',dict(baseline=BASELINE,precheck_commit=PRECHECK_COMMIT,
        source_commit=os.getenv('GITHUB_SHA','local'),source_sha256=ev.sha(__file__),
        immutable=guard,python=platform.python_version(),numpy=np.__version__,
        validation_accessed=False,test_accessed=False,columns=COLUMNS))
    store=ev.ex.Store(args.data_root)
    save(args.output/'split.json',partition(store.manifest['records']))
    traces={};bagcounters=[];started=time.perf_counter();cpu=time.process_time()
    for idx,bag in enumerate(store.plan['splits']['train']):
        # Journal the authorized intent BEFORE the original role-checked loader.
        save(args.output/'access.json',dict(validation_accessed=False,test_accessed=False,
            intent=dict(bag=bag,purpose='train',topics=list(ev.ex.CHANNELS)),completed=store.access))
        events,refs=store.load(bag,'train')
        assert refs=={'master':[],'rover':[]}
        data,counters,runtime=trace(events,check_state=idx==0)
        if idx==0:
            c,ro=profile();old=ev.Observer
            try:
                ev.Observer=lambda cfg:GuardedReadoutObserver(cfg,readout=ro)
                direct,info=ev.replay(events,c,dict(rate_hz=20.,alignment_delay_s=0.))
                ev.Observer=lambda cfg:Probe(cfg,readout=ro,check_state=True)
                captured,captured_info=ev.replay(events,c,dict(rate_hz=20.,alignment_delay_s=0.))
                assert np.array_equal(direct,captured,equal_nan=True) and info==captured_info
                scored=ev.score(events,refs,{'baseline_v2':c,'balanced_physics':c},dict(rate_hz=20.,alignment_delay_s=0.))
            finally:ev.Observer=old
            save(args.output/'baseline_sanity.json',dict(passed=True,bag=bag,outputs=len(direct),
                schedule_outputs_and_every_base_state_equal=True,official_scorer=scored,
                accuracy_reference='N/A: train GNSS forbidden, both receiver targets empty'))
        traces[bag]=data
        (args.output/'traces').mkdir(exist_ok=True)
        np.savez_compressed(args.output/'traces'/(bag+'.npz'),trace=data)
        bagcounters.append(dict(bag=bag,group=store.records[bag]['group'],counters=counters,runtime=runtime))
        print('TRAIN',bag,'trusted',len(data),'tight',counters['tight'],flush=True)
    save(args.output/'access.json',dict(validation_accessed=False,test_accessed=False,completed=store.access))
    result,groups,bags=analyze(traces,store.manifest['records'])
    result.update(train_bags=len(traces),elapsed_wall_s=time.perf_counter()-started,
                  process_cpu_s=time.process_time()-cpu,total_trusted=sum(len(a) for a in traces.values()))
    save(args.output/'result.json',result);save(args.output/'activation.json',bagcounters)
    write_csv(args.output/'per_group.csv',groups);write_csv(args.output/'per_bag.csv',bags)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
