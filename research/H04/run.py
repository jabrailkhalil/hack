"""Single preregistered H04 candidate. No parameter search or final-test loader.

The v6 validation worker, metric functions, masks, faults and decision gates
are imported unchanged. Only its model factory is supplied by this runner.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/research_v6'), str(ROOT/'src/reserve_odometry')]
import compare as v6
from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.timeline import Timeline

ev, ex, np = v6.ev, v6.ex, v6.np
BASE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
NAME = 'h04_regime_quality_v1'
OPS = dict(rate_hz=20., alignment_delay_s=0.)
# Fixed before data IO: diagnostic prefix for every train bag, not a tuned subset.
TRAIN_PREFIX_S = 180.
PINNED = (
    'tools/finalization/evaluate.py', 'tools/research_v6/compare.py',
    'tools/research_v3/experiment.py', 'tools/research_v3/manifest.py',
    'tools/export_bags.py', 'research/plan_v3.json', 'research/split_v3.json',
    'src/reserve_odometry/reserve_odometry/timeline.py',
    'src/reserve_odometry/reserve_odometry/node.py',
    'src/reserve_odometry/reserve_odometry/route.py',
    'src/reserve_odometry/config/adaptive_v5.json',
    'src/reserve_odometry/config/adaptive_v5.yaml',
    'src/reserve_odometry/config/default.yaml',
    'src/reserve_odometry/config/candidates_v3/balanced_physics.json')
CANDIDATE_FILES = (
    'research/H04/PLAN.md', 'research/H04/config.json', 'research/H04/config.yaml',
    'research/H04/algorithm.patch', 'research/H04/run.py',
    'research/H04/tests/test_schedule.py',
    'src/reserve_odometry/reserve_odometry/core.py',
    'src/reserve_odometry/reserve_odometry/adaptation.py')


def git_bytes(path):
    return subprocess.check_output(['git', 'show', BASE+':'+path], cwd=ROOT)


def verify_pinned():
    for path in PINNED:
        if (ROOT/path).read_bytes() != git_bytes(path):
            raise AssertionError('Pinned evaluator/runtime/config changed: '+path)
    if not hasattr(Config(), 'adaptation_schedule_enabled'):
        raise AssertionError('Apply the explicit H04 algorithm.patch before running')
    if json.loads((ROOT/'research/H04/config.json').read_text())['config'] != (
            json.loads((ROOT/'src/reserve_odometry/config/adaptive_v5.json').read_text())['config'] |
            {'adaptation_schedule_enabled': 1.0}):
        raise AssertionError('The singleton candidate differs from the preregistered profile')
    return {p: ev.sha(ROOT/p) for p in PINNED}


def configurations():
    old=json.loads((ROOT/'src/reserve_odometry/config/candidates_v3/balanced_physics.json').read_text())['config']
    adaptive=json.loads((ROOT/'src/reserve_odometry/config/adaptive_v5.json').read_text())['config']
    candidate=json.loads((ROOT/'research/H04/config.json').read_text())['config']
    return {'baseline_v2': Config(**old), 'balanced_physics': Config(**adaptive), NAME: Config(**candidate)}


def diagnostics(events, config, fault=None):
    """Extra descriptive observations, never substituted for any evaluator metric."""
    obs=Observer(config);timeline=Timeline(obs,rate_hz=20.,delay_s=0.)
    tau=Counter();transitions=Counter();phase_tau=Counter();changes=Counter()
    last_regime=None;last_disturbance=None;outputs=0
    for t,ch,value in events:
        ch=int(ch)
        if fault and fault['start']<=t<fault['end']:
            if fault['kind']=='dropout' and ch in (1,2):continue
            if fault['kind']=='lock' and ch in (1,2):value=0.
            if fault['kind']=='bias' and ch==1:value+=5.
        timeline.ingest(ch,Sample(float(t),float(value)))
        for e,held in timeline.advance():
            if e.mode=='WAITING_FOR_INITIALIZATION':continue
            outputs+=1
            current=obs.adaptation_schedule.regime
            if current is not None and last_regime is not None and current!=last_regime:
                transitions[f'{last_regime}->{current}']+=1
            last_regime=current
            key=str(obs.adaptation_tau);tau[key]+=1
            if fault:
                phase='before' if e.t<fault['start'] else ('event' if e.t<fault['end'] else 'recovery')
                phase_tau[phase+'/'+key]+=1
            if last_disturbance is not None and e.disturbance!=last_disturbance:
                changes[e.mode+'/'+key]+=1
            last_disturbance=e.disturbance
    return dict(outputs=outputs,tau_output_ticks=dict(tau),regime_transitions=dict(transitions),
                phase_tau_output_ticks=dict(phase_tau),disturbance_changes=dict(changes),
                note='Tau on non-FUSED ticks is diagnostic only; no learning on those ticks except stop resets.')


def train_bag(bag):
    store=ex.Store();events,refs=store.load(bag,'train')
    if any(refs.values()):raise AssertionError('Train references must remain inaccessible')
    events=events[events[:,0]<=TRAIN_PREFIX_S]
    models=configurations();a,ar=ev.replay(events,models['balanced_physics'],OPS)
    b,br=ev.replay(events,models[NAME],OPS)
    if a.shape!=b.shape or not np.array_equal(a[:,0],b[:,0]):
        raise AssertionError('Train output schedule differs: '+bag)
    if br['causal_errors'] or br['resets']:raise AssertionError('Train causality/reset: '+bag)
    return dict(bag=bag,group=store.records[bag]['group'],input_events=len(events),outputs=len(b),
                clean_rmse=None,fault_rmse=None,reference_available=False,
                baseline_runtime=ar,candidate_runtime=br,
                diagnostics=diagnostics(events,models[NAME]),access=store.access)


def validation_bag(bag):
    # This is a factory seam, not a replacement of score, replay, gates or faults.
    v6.configurations=configurations
    return v6.validate_bag(bag)


def source_manifest():
    return {p:ev.sha(ROOT/p) for p in CANDIDATE_FILES}


def provenance():
    return dict(hypothesis='H04',baseline_commit=BASE,candidate=NAME,
                source_commit=os.environ.get('GITHUB_SHA',subprocess.check_output(
                    ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()),
                run_id=os.environ.get('GITHUB_RUN_ID','local'),
                run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT','1'),
                utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                python=platform.python_version(),numpy=np.__version__,
                source_sha256=source_manifest(),pinned_sha256=verify_pinned(),
                operational=OPS,test_evaluated=False)


def export_csv(output,clean,stress,decision):
    import csv
    names=('v4_default','v5_adaptive_05s',NAME)
    rows=[]
    for kind,data in [('clean',clean),('fault',stress)]:
        for row in data:
            for receiver,scores in row['receivers'].items():
                for name in names:
                    m=scores[name]
                    rows.append(dict(kind=kind,bag=row['bag'],group=row['group'],receiver=receiver,model=name,
                        fault=row.get('fault',{}).get('kind'),start=row.get('fault',{}).get('start'),
                        end=row.get('fault',{}).get('end'),
                        **{k:m.get(k) for k in ('n','coverage','rmse','mae','bias','p95','event_rmse',
                                                'false_stop_samples','recovery_s')},
                        distance_rmse=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m')))
    with (output/'per_bag.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    entries=[dict(model=n,**s) for n,s in decision['candidates'].items()]
    with (output/'aggregate.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(entries[0]));writer.writeheader();writer.writerows(entries)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['train','freeze','validation'])
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--frozen',type=Path)
    p.add_argument('--train-result',type=Path)
    p.add_argument('--workers',type=int,default=2)
    args=p.parse_args()
    if not 1<=args.workers<=2:raise ValueError('Use one or two workers')
    prov=provenance();store=ex.Store()
    if args.stage=='freeze':
        if args.output.exists():raise FileExistsError('Never overwrite a freeze')
        if not args.train_result:raise ValueError('--train-result is required')
        train=json.loads(args.train_result.read_text())
        if train['source_sha256']!=prov['source_sha256'] or not train['passed']:
            raise AssertionError('Train check does not match the frozen candidate')
        ev.save(args.output,dict(**prov,selected_candidate=NAME,variant_budget=1,
             train_result_sha256=ev.sha(args.train_result),validation_bags=store.plan['splits']['validation'],
             models={k:asdict(c) for k,c in configurations().items()},
             frozen_before_validation=True,selection='singleton a priori; no metric-based tuning'))
        print('FROZEN',args.output,flush=True);return
    args.output.mkdir(parents=True,exist_ok=False)
    ev.save(args.output/'started.json',prov);started=time.perf_counter()
    if args.stage=='train':
        rows=[];access=[]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for row in pool.map(train_bag,store.plan['splits']['train']):
                rows.append(row);access.extend(row['access'])
                ev.save(args.output/'bags'/(row['bag']+'.json'),row)
                ev.save(args.output/'access.json',dict(test_evaluated=False,access=access))
                print('TRAIN_CHECKPOINT',row['bag'],row['outputs'],flush=True)
        ev.save(args.output/'results.json',dict(**prov,stage='train',passed=True,bags=rows,
                    prefix_s=TRAIN_PREFIX_S,elapsed_s=time.perf_counter()-started,
                    accuracy_evidence=False,parameters_fitted=False))
        return
    if not args.frozen:raise ValueError('--frozen is required before validation')
    frozen=json.loads(args.frozen.read_text())
    if (frozen['source_sha256']!=prov['source_sha256'] or frozen['pinned_sha256']!=prov['pinned_sha256'] or
            frozen['validation_bags']!=store.plan['splits']['validation'] or
            frozen['selected_candidate']!=NAME or not frozen['frozen_before_validation']):
        raise AssertionError('Frozen candidate/evaluator/split changed')
    clean=[];stress=[];access=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for row,faults,journal in pool.map(validation_bag,frozen['validation_bags']):
            clean.append(row);stress.extend(faults);access.extend(journal)
            ev.save(args.output/'bags'/(row['bag']+'.json'),dict(clean=row,stress=faults))
            ev.save(args.output/'access.json',dict(test_evaluated=False,access=access))
            print('VALIDATION_CHECKPOINT',row['bag'],flush=True)
    reproduction=v6.reproduce_published_v5(clean)
    names=['v4_default','v5_adaptive_05s',NAME]
    decision=v6.decide(clean,stress,names)
    ev.save(args.output/'results.json',dict(**prov,clean=clean,stress=stress,
                models={v6.ALIASES.get(n,n):asdict(c) for n,c in configurations().items()},
                baseline_reproduction=reproduction,freeze_sha256=ev.sha(args.frozen),
                elapsed_s=time.perf_counter()-started))
    ev.save(args.output/'v6_decision.json',decision)
    base=decision['candidates']['v5_adaptive_05s'];cand=decision['candidates'][NAME]
    pooled_change=cand['pooled_rmse']/base['pooled_rmse']-1
    accepted=cand['eligible'] and pooled_change<=.005
    ev.save(args.output/'decision.json',dict(candidate=NAME,accuracy_gates_passed=accepted,
        conclusion='подтверждена на повторно используемом validation' if accepted else 'отвергнута',
        rejection_reasons=cand['rejection_reasons']+(['pooled_rmse_regression'] if pooled_change>.005 else []),
        pooled_rmse_change_vs_v5=pooled_change,test_evaluated=False,
        merge_ready=False,runtime_acceptance='Separate ROS and resource checks required; no automatic promotion',
        independent_test=False,candidates=decision['candidates']))
    export_csv(args.output,clean,stress,decision)
    print(json.dumps(json.loads((args.output/'decision.json').read_text()),ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
