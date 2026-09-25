"""Isolated R2/H17 factory, diagnostics and admission; frozen metrics are imported.

No test role. No train reference. No changing Timeline, matching or old pins.
All predictor inputs remain the three vehicle channels. Labels stay outside it.
"""
import argparse
from bisect import bisect_right
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import resource
import sqlite3
import subprocess
import sys
import time
import csv

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT/'tools/finalization'), str(ROOT/'src/reserve_odometry')]
import evaluate as ev
from reserve_odometry.core import Config, Sample, clip
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.command_deadtime import CommandDeadtimeObserver
from reserve_odometry.timeline import Timeline
ex, np = ev.ex, ev.np
BASE = '65bba39ed05c781f3f69a65c02f69931152cbfd9'
OPS = {'rate_hz': 20., 'alignment_delay_s': 0.}
DELAYS = {'H17_L050': .05, 'H17_L100': .10, 'H17_L200': .20}
ALIASES = {'baseline_v2': 'R2_v7', 'balanced_physics': 'R2_off'}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


v6 = module('h17_frozen_v6', 'tools/research_v6/compare.py')
grd = module('h17_frozen_guarded', 'tools/research_guarded/compare.py')


def save(path, value):
    ev.save(path, value)


def read(path):
    return json.loads(Path(path).read_text())


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def profile():
    data = read(ROOT/'src/reserve_odometry/config/guarded_readout_v7.json')
    values = {}
    for line in (ROOT/'src/reserve_odometry/config/guarded_readout_v7.yaml').read_text().splitlines():
        key, sep, val = line.strip().partition(':')
        if sep and (key.startswith(('model.', 'readout.')) or key in ('rate_hz', 'alignment_delay_s')):
            values[key] = float(val)
    assert {k[6:]: v for k, v in values.items() if k.startswith('model.')} == data['config']
    assert {k[8:]: v for k, v in values.items() if k.startswith('readout.')} == data['readout']
    assert data['readout'] == {'gain': 1., 'holdoff_s': .5}
    assert data['config']['actuator_tau_s'] == .3927619145850434
    assert data['config']['adaptation_tau_s'] == .5 and data['config']['wheel_time_compensation'] == 0
    assert values['rate_hz'] == 20. and values['alignment_delay_s'] == 0.
    return data


def preflight():
    pins = read(HERE/'PINS.json')
    for path, expected in pins['source_sha256'].items():
        if ev.sha(ROOT/path) != expected:
            raise ValueError('Pinned source differs: '+path)
    profile()
    paths = list(pins['source_sha256']) + [
        'src/reserve_odometry/reserve_odometry/command_deadtime.py',
        'research/R2/H17/driver.py', 'research/R2/H17/PINS.json', 'research/R2/H17/PLAN.md']
    paths += [str(p.relative_to(ROOT)) for p in (HERE/'tests').glob('*.py')]
    return {p: ev.sha(ROOT/p) for p in sorted(set(paths))}


class RoleStore(ex.Store):
    """Explicit development role; permission check precedes checksum and SQLite."""
    def __init__(self, root, journal):
        super().__init__(root)
        self.journal = journal

    def load_role(self, bag, role, references=True):
        row = self.records[bag]
        if role not in ('train', 'development', 'validation') or row['split'] != role:
            raise PermissionError('H17 role denied before IO: '+bag+'/'+role)
        if role == 'train':
            references = False
        allowed = list(ex.CHANNELS) + (list(ex.REFS) if references else [])
        entry = dict(bag=bag, purpose=role, sha256=row['sha256'], topics=allowed, state='before_read')
        self.access.append(entry)
        save(self.journal, dict(test_evaluated=False, access=self.access))
        if role in ('train', 'validation'):
            # Exact legacy loader: train cannot expose references.
            events, refs = super().load(bag, role)
            self.access.pop()  # Keep the before/after journal, not a duplicated legacy entry.
        else:
            path = self.root/bag/(bag+'_0.db3')
            if ev.sha(path) != row['sha256']:
                raise ValueError('Bag checksum mismatch: '+bag)
            events, refs = [], {'master': [], 'rover': []}
            with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as con:
                query = ('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                         'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
                for topic, typ, raw in con.execute(query, allowed):
                    stamp, values = ev.decode(raw, typ)
                    t = (stamp-row['sensor_start_ns'])/1e9
                    if topic in ex.CHANNELS:
                        ch = ex.CHANNELS[topic]
                        events.append((t, ch, float(values[0])/(15 if ch == 0 else 3.6)))
                    else:
                        speed = math.hypot(float(values[0]), float(values[1]))
                        if math.isfinite(speed):
                            refs[ex.REFS[topic]].append((t, speed))
            events = np.asarray(events, float)
        entry['state'] = 'completed'
        save(self.journal, dict(test_evaluated=False, access=self.access))
        return events, refs


class CheckedOff(CommandDeadtimeObserver):
    """Every published field and every canonical state field must match, per tick."""
    def __init__(self, config, *, readout):
        self.reference = GuardedReadoutObserver(config, readout=readout)
        super().__init__(config, readout=readout, delay_s=0.)

    def reset(self, **kwargs):
        super().reset(**kwargs)
        self.reference.reset(**kwargs)

    def step(self, *args, **kwargs):
        result = super().step(*args, **kwargs)
        target = self.reference.step(*args, **kwargs)
        if result != target:
            raise AssertionError('Off published Estimate mismatch')
        for key, value in vars(self.reference).items():
            if getattr(self, key) != value:
                raise AssertionError('Off canonical state differs: '+key)
        return result


def transitions(events):
    grid = ex.grid_channels(events)
    if grid is None:
        return [], None
    t, u, f, r, valid = grid
    modes = np.where(u > .04, 1, np.where(u < -.04, -1, 0))
    idx = np.flatnonzero(valid[1:] & valid[:-1] & (modes[1:] != modes[:-1]) & ((f[1:]+r[1:])/2 > .5))+1
    return [dict(t=float(t[i]), mode=int(modes[i]), speed=float((f[i]+r[i])/2)) for i in idx], grid


def extra_windows(events, switches, grid):
    """Preregistered diagnostics, never replace original-suite admission."""
    end = float(events[:, 0].max())
    selected = set()
    faults = []
    for item in switches:
        if item['mode'] not in selected and 25 < item['t'] < end-16 and item['speed'] > 1:
            selected.add(item['mode'])
            anchor = item['t']+.05
            for kind, duration in [('dropout', 5.), ('controller_loss', 1.)]:
                faults.append(dict(kind=kind, start=anchor, end=anchor+duration,
                                   diagnostic='transition_to_'+str(item['mode'])))
    if grid is not None:
        t, u, f, r, valid = grid
        ix = np.flatnonzero(valid & ((f+r)/2 > 1.) & ((f+r)/2 < 2.) &
                            (t > max(25., .1*t[-1])) & (t < t[-1]-25.))
        if len(ix):
            anchor = float(t[ix[0]])
            faults.append(dict(kind='lock', start=anchor, end=anchor+3., diagnostic='low_speed'))
    for fault in faults:
        window = events[(events[:, 0] >= fault['start']-20.) & (events[:, 0] <= fault['end']+10.1)]
        if fault['kind'] == 'controller_loss':
            # Algorithm never sees an oracle flag. Frozen replay ignores this kind.
            window = window[~((window[:, 1] == 0) & (window[:, 0] >= fault['start']) & (window[:, 0] < fault['end']))]
        yield fault, window


class Recorder:
    """Offline wrapper; no diagnostics or references are sent into the observer."""
    def __init__(self, observer, switches, fault):
        self.observer = observer
        self.c = observer.c
        self.switches = switches
        self.switch_times = [s['t'] for s in switches]
        self.fault = fault
        selected = {}
        for s in switches:
            selected.setdefault(s['mode'], s['t'])
        self.windows = [(x-.5, x+2) for x in selected.values()]
        if fault:
            self.windows = [(fault['start']-.5, fault['start']+1), (fault['end']-.5, fault['end']+1)]
        self.traces, self.phase = [], []
        self.counts = Counter()
        self.history_peak = 0

    def __getattr__(self, key):
        return getattr(self.observer, key)

    def reset(self, **kwargs):
        self.observer.reset(**kwargs)

    def step(self, t, command=None, front=None, rear=None):
        obs = self.observer
        before = obs.disturbance
        estimate = obs.step(t, command, front, rear)
        u = 0. if estimate.command_stale else clip(command.value, -1., 1.)
        status = getattr(obs, 'delay_status', 'OFF')
        delayed = u if status == 'OFF' else obs.delayed_command
        self.counts['ticks'] += 1
        self.counts['stale_ticks'] += int(estimate.command_stale)
        self.counts[status] += 1
        self.counts['changed_selected_ticks'] += int(status == 'DELAYED' and u != delayed)
        self.history_peak = max(self.history_peak, getattr(obs, 'command_history_peak', 0))
        if status == 'DELAYED' and obs.delayed_stamp > t-obs.delay_s:
            raise AssertionError('Selected command after t-L')
        if self.history_peak > 64:
            raise AssertionError('Unbounded command memory')
        if not all(math.isfinite(getattr(estimate, k)) for k in ('t', 'v', 's', 'a', 'variance_v', 'variance_s', 'disturbance')):
            raise AssertionError('Nonfinite Estimate')
        i = bisect_right(self.switch_times, t)-1
        if i >= 0 and 0 <= t-self.switch_times[i] < 2. and estimate.mode != 'WAITING_FOR_INITIALIZATION':
            self.phase.append((t, estimate.v, self.switches[i]['mode']))
        if any(a <= t <= b for a, b in self.windows):
            self.traces.append(dict(t=t, u=u, u_delayed=delayed, delayed_stamp=getattr(obs, 'delayed_stamp', None),
                delay_status=status, drive_a=obs.drive_a, disturbance_before=before, disturbance=obs.disturbance,
                inner_v=obs.v, published_v=estimate.v, published_s=estimate.s, mode=estimate.mode,
                front_status=estimate.front_status, rear_status=estimate.rear_status, command_stale=estimate.command_stale))
        return estimate

    def diagnostics(self, refs):
        phases = {}
        a = np.asarray(self.phase, float).reshape(-1, 3)
        if len(a):
            for receiver, vals in refs.items():
                target = ex.match(vals, a[:, 0])
                for mode in (-1, 0, 1):
                    phases[receiver+'/'+str(mode)] = ex.metrics(a[:, 0], a[:, 1], target,
                                                                 np.isfinite(target) & (a[:, 2] == mode))
        return dict(counts=dict(self.counts), history_peak=self.history_peak, phase=phases, traces=self.traces)


def paired(events, refs, delays, switches, fault=None, collect=True):
    p = profile()
    models = {name: Config(**p['config']) for name in ['baseline_v2', 'balanced_physics', *delays]}
    names = {id(c): name for name, c in models.items()}
    recorders = {}
    def factory(config):
        name = names[id(config)]
        opts = dict(readout=ReadoutConfig(**p['readout']))
        if name == 'baseline_v2':
            observer = GuardedReadoutObserver(config, **opts)
        elif name == 'balanced_physics':
            observer = CheckedOff(config, **opts)
        else:
            observer = CommandDeadtimeObserver(config, delay_s=delays[name], **opts)
        if collect:
            recorders[name] = Recorder(observer, switches, fault)
            return recorders[name]
        return observer
    old = ev.Observer
    try:
        ev.Observer = factory
        result = ev.score(events, refs, models, OPS, fault)
    finally:
        ev.Observer = old
    # All metric definitions above are the original score; only aliases change.
    if result['runtime']['baseline_v2'] != result['runtime']['balanced_physics']:
        raise AssertionError('Canonical/off runtime counters differ')
    for receiver, scores in result['receivers'].items():
        other = {k: v for k, v in scores['balanced_physics'].items() if not k.startswith('common_')}
        if scores['baseline_v2'] != other:
            raise AssertionError('Canonical/off metrics differ: '+receiver)
    for old_name, new in ALIASES.items():
        result['runtime'][new] = result['runtime'].pop(old_name)
        for scores in result['receivers'].values():
            scores[new] = scores.pop(old_name)
    result['diagnostics'] = {ALIASES.get(n,n): r.diagnostics(refs) for n,r in recorders.items()}
    result['canonical_off_exact'] = True
    return result


def one_bag(args):
    bag, role, root, output, delays = args
    output = Path(output)
    store = RoleStore(Path(root), output/'access'/(bag+'.json'))
    events, refs = store.load_role(bag, role)
    switches, grid = transitions(events)
    meta = dict(bag=bag, group=store.records[bag]['group'], role=role)
    clean = dict(**meta, **paired(events, refs, delays, switches))
    stress, extra = [], []
    if role != 'train':
        for fault, window in grd.fault_windows(events):
            stress.append(dict(**meta, fault=fault, **paired(window, refs, delays, switches, fault)))
        for fault, window in extra_windows(events, switches, grid):
            extra.append(dict(**meta, fault=fault, **paired(window, refs, delays, switches, fault)))
    result = dict(clean=clean, stress=stress, extra=extra, transitions=switches, access=store.access)
    save(output/'bags'/(bag+'.json'), result)
    print('CHECKPOINT', role, bag, 'outputs', clean['outputs'], 'transitions', len(switches), flush=True)
    return result


def regression(value, baseline, fraction):
    if value is None or baseline is None:
        return True
    return value > (baseline*(1+fraction) if baseline > 0 else 1e-12)


def admission(clean, stress, extra, name, require_gain):
    b, c = v6.summary(clean, stress, 'R2_v7'), v6.summary(clean, stress, name)
    reasons = []
    for metric, limit in [('clean_rmse', .005), ('fault_rmse', .005), ('pooled_rmse', .005), ('distance_rmse', .01)]:
        if regression(c[metric], b[metric], limit):
            reasons.append('aggregate_regression:'+metric)
    gains = {k: (1-c[k]/b[k] if b[k] not in (None,0) and c[k] is not None else None)
             for k in ('clean_rmse', 'fault_rmse')}
    if require_gain and not ((gains['clean_rmse'] or 0) >= .02 or (gains['fault_rmse'] or 0) >= .05):
        reasons.append('insufficient_gain')
    for suite, rows in [('clean',clean), ('original',stress), ('extra',extra)]:
        for row in rows:
            rt = row['runtime'][name]
            if rt['causal_errors'] or rt['resets']:
                reasons.append('causality_or_reset:'+suite+'/'+row['bag'])
            for receiver, scores in row['receivers'].items():
                bm, cm = scores['R2_v7'], scores[name]
                label = suite+'/'+row['bag']+'/'+receiver+'/'+str(row.get('fault',{}))
                if bm['n'] != cm['n'] or bm['coverage'] != cm['coverage']:
                    reasons.append('coverage:'+label)
                if cm['false_stop_samples'] > bm['false_stop_samples']:
                    reasons.append('false_stop:'+label)
                if suite == 'clean' and bm['rmse'] is not None:
                    if cm['rmse'] is None or cm['rmse'] > bm['rmse']+max(.005,.05*bm['rmse']):
                        reasons.append('per_bag_regression:'+label)
                if suite != 'clean' and bm.get('event_rmse') is not None and bm.get('recovery_s') is not None and cm.get('recovery_s') is None:
                    reasons.append('new_unrecovered:'+label)
    return dict(passed=not reasons, rejection_reasons=sorted(set(reasons)), gains=gains,
                delta={k: c[k]-b[k] if c[k] is not None and b[k] is not None else None for k in b}, summary=c)


def tables(output, clean, stress, extra, names, aggregates):
    with (output/'aggregate.csv').open('w') as f:
        writer=csv.DictWriter(f, ['model', *next(iter(aggregates.values())).keys()]);writer.writeheader()
        for name, row in aggregates.items(): writer.writerow(dict(model=name,**row))
    keys=['suite','bag','group','receiver','model','kind','start','end','n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s','false_stop_samples','distance']
    with (output/'per_bag.csv').open('w') as f:
        writer=csv.DictWriter(f,keys);writer.writeheader()
        for suite, rows in [('clean',clean),('original',stress),('extra',extra)]:
            for row in rows:
                for receiver, scores in row['receivers'].items():
                    for name in names:
                        m=scores[name];fault=row.get('fault',{})
                        writer.writerow(dict(suite=suite,bag=row['bag'],group=row['group'],receiver=receiver,model=name,
                            **{k:fault.get(k) for k in ['kind','start','end']},
                            **{k:m.get(k) for k in ['n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s','false_stop_samples']},
                            distance=v6.metric_value(m,'distance')))


def run_stage(args, hashes):
    role=args.stage
    delays=DELAYS if role=='development' else {}
    if role=='validation':
        if not args.freeze or not args.freeze_commit:
            raise PermissionError('Validation requires separately published freeze commit')
        frozen=read(args.freeze)
        if frozen['source_sha256'] != hashes or frozen['baseline'] != BASE or frozen['selected'] not in DELAYS:
            raise ValueError('Frozen sources/configuration differ')
        # A real Git commit must contain exactly the supplied freeze, before IO.
        rel=str(Path(args.freeze).resolve().relative_to(ROOT))
        if json.loads(git('show',args.freeze_commit+':'+rel)) != frozen:
            raise ValueError('Freeze not committed at declared SHA')
        git('merge-base','--is-ancestor',args.freeze_commit,'HEAD')
        delays={frozen['selected']:DELAYS[frozen['selected']]}
    store=ex.Store(args.data_root)
    clean,stress,extra,journal,switches=[],[],[],[],[]
    tasks=[(bag,role,str(args.data_root),str(args.output),delays) for bag in store.plan['splits'][role]]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(one_bag,tasks):
            clean.append(row['clean']);stress+=row['stress'];extra+=row['extra'];journal+=row['access']
            switches.append(dict(bag=row['clean']['bag'],group=row['clean']['group'],transitions=row['transitions']))
    names=['R2_v7','R2_off',*delays]
    aggregates={name:v6.summary(clean,stress,name) for name in names}
    for name in names:
        aggregates[name].update(clean_mae=v6.macro(clean,name,'mae'),clean_bias=v6.macro(clean,name,'bias'),
            clean_p95=v6.macro(clean,name,'p95'),recovery_s=v6.macro(stress,name,'recovery_s'))
    result=dict(baseline=BASE,stage=role,source_sha256=hashes,models={n:dict(profile=profile(),delay_s=delays.get(n,0.)) for n in names},
        clean=clean,stress=stress,extra=extra,aggregates=aggregates,transitions=switches,
        canonical_off_exact=all(r['canonical_off_exact'] for r in clean+stress+extra),test_evaluated=False)
    save(args.output/'results.json',result);save(args.output/'access.json',dict(test_evaluated=False,access=journal))
    tables(args.output,clean,stress,extra,names,aggregates)
    if role=='train':
        save(args.output/'decision.json',dict(stage='train',fitted=False,train_bags=len(clean),train_references_read=False,canonical_off_exact=True))
        return
    checks={name:admission(clean,stress,extra,name,role=='validation') for name in delays}
    transition_groups={r['group'] for r in switches if r['transitions']}
    total_transitions=sum(len(r['transitions']) for r in switches)
    ref_groups={r['group'] for r in clean if any(s['R2_v7']['rmse'] is not None for s in r['receivers'].values())}
    coverage={name:dict(changed_selected_ticks=sum(r['diagnostics'][name]['counts'].get('changed_selected_ticks',0) for r in clean),
        qualifying_transitions=total_transitions,transition_groups=len(transition_groups),reference_groups=len(ref_groups),
        history_peak=max(r['diagnostics'][name]['history_peak'] for r in clean)) for name in delays}
    for name,c in coverage.items():
        c['passed']=c['changed_selected_ticks']>=100 and c['qualifying_transitions']>=20 and c['transition_groups']>=3 and c['reference_groups']>=3
    eligible=[n for n in delays if checks[n]['passed'] and coverage[n]['passed']]
    selected=min(eligible,key=lambda n:(aggregates[n]['clean_rmse'],aggregates[n]['fault_rmse'],delays[n])) if eligible else None
    if not any(c['passed'] for c in coverage.values()): verdict='INCONCLUSIVE'
    elif selected is None: verdict='REJECTED'
    else: verdict='SELECTED_FOR_FREEZE' if role=='development' else 'ACCURACY_PASSED_PENDING_ROS'
    by_group={}
    for group in sorted(ref_groups):
        rows=[r for r in clean if r['group']==group]
        values={n:v6.macro(rows,n,'rmse') for n in ['R2_v7',*delays]}
        best=min(v for v in values.values() if v is not None)
        by_group[group]=dict(rmse=values,optima=[n for n,v in values.items() if v is not None and abs(v-best)<=1e-10])
    decision=dict(stage=role,verdict=verdict,selected=selected,checks=checks,coverage=coverage,
                  group_optima=by_group,ready_to_merge=False,validation_opened=role=='validation',test_evaluated=False,
                  qualification='Group optima are descriptive, not fitted physical delays; reused validation is not independent test.')
    save(args.output/'decision.json',decision)
    print(json.dumps(decision,indent=2),flush=True)


def timed_replay(events, delay):
    p=profile();cfg=Config(**p['config']);opts=dict(readout=ReadoutConfig(**p['readout']))
    observer=GuardedReadoutObserver(cfg,**opts) if delay==0 else CommandDeadtimeObserver(cfg,delay_s=delay,**opts)
    step_cpu=step_wall=0.;count=0;start=float(events[:,0].min())+10.
    class Timed:
        c=cfg
        def __getattr__(self,k): return getattr(observer,k)
        def reset(self): return observer.reset()
        def step(self,t,*inputs):
            nonlocal step_cpu,step_wall,count
            a=time.process_time_ns();b=time.perf_counter_ns()
            result=observer.step(t,*inputs)
            c=time.perf_counter_ns();d=time.process_time_ns()
            if t>=start:step_cpu+=d-a;step_wall+=c-b;count+=1
            return result
    timeline=Timeline(Timed(),rate_hz=20.,delay_s=0.);out=[];cpu=wall=None
    for t,ch,value in events:
        if cpu is None and t>=start:cpu=time.process_time_ns();wall=time.perf_counter_ns()
        timeline.ingest(int(ch),Sample(float(t),float(value)))
        for estimate,_ in timeline.advance():out.append((estimate.t,estimate.v,estimate.s))
    elapsed_cpu=(time.process_time_ns()-cpu)/1e9;elapsed_wall=(time.perf_counter_ns()-wall)/1e9
    return dict(delay_s=delay,replay_cpu_s=elapsed_cpu,replay_wall_s=elapsed_wall,step_cpu_s=step_cpu/1e9,
        step_wall_s=step_wall/1e9,post_warmup_steps=count,outputs=len(out),output_sha256=hashlib.sha256(np.asarray(out).tobytes()).hexdigest(),
        process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)


def cost(args,hashes):
    bag='30618_0652866c';store=RoleStore(args.data_root,args.output/'access.json')
    events,_=store.load_role(bag,'development',references=False)
    events=events[events[:,0]<=events[:,0].min()+120.]
    results=[]
    for name,delay in DELAYS.items():
        for repeat in range(3):
            for order in ('AB','BA'):
                for label in order:
                    result=timed_replay(events,0. if label=='A' else delay)
                    results.append(dict(candidate=name,repeat=repeat,order=order,label=label,**result))
    save(args.output/'cost.json',dict(bag=bag,source_sha256=hashes,warmup_s=10,window_s=120,results=results,
        threads={k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS')},
        caveat='Instrumented offline Python timings, not installed ROS latency. RSS is whole-process high-water, not incremental state.'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['train','development','cost','validation'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--data-root',type=Path,default=ROOT/'dataset/data')
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--freeze',type=Path);parser.add_argument('--freeze-commit')
    args=parser.parse_args()
    if not 1<=args.workers<=4:raise ValueError('workers must be 1..4')
    hashes=preflight();args.output.mkdir(parents=True,exist_ok=False)
    try:commit=git('rev-parse','HEAD')
    except (subprocess.SubprocessError,FileNotFoundError):commit='local-source-copy'
    save(args.output/'started.json',dict(baseline=BASE,source_commit=commit,source_sha256=hashes,
        command=sys.argv,python=platform.python_version(),numpy=np.__version__,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        role=args.stage,test_evaluated=False,canonical_class='GuardedReadoutObserver',output='returned Estimate.v/s'))
    started=time.perf_counter()
    if args.stage=='cost':cost(args,hashes)
    else:run_stage(args,hashes)
    save(args.output/'completed.json',dict(elapsed_s=time.perf_counter()-started,success=True))


if __name__=='__main__':main()
