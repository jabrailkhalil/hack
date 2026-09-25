"""H07 preregistered train-only identification and one frozen validation.

The baseline evaluator, timestamps, masks and fault generator are imported
unchanged. No command line path opens final-test measurements.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/research_v6'))
import compare as common

ev, ex, np = common.ev, common.ev.ex, common.np
BASELINE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
PROFILE = 'src/reserve_odometry/config/adaptive_v5.json'
CORE = 'src/reserve_odometry/reserve_odometry/core.py'
PROTOCOL = 'research/H07/PROTOCOL.md'
VARIANTS = [('T05_B10', .5, 1.), ('T10_B05', 1., .5),
            ('T20_B10', 2., 1.), ('T10_B20', 1., 2.),
            ('T05_B20', .5, 2.), ('T20_B05', 2., .5)]
UNCHANGED = [
    'tools/finalization/evaluate.py', 'tools/research_v3/experiment.py',
    'tools/research_v3/manifest.py', 'tools/research_v6/compare.py',
    'tools/export_bags.py', 'tools/get_dataset.py', 'requirements-research.txt',
    'research/plan_v3.json', 'research/split_v3.json', PROFILE,
    'src/reserve_odometry/config/adaptive_v5.yaml',
    'src/reserve_odometry/config/default.yaml',
    'src/reserve_odometry/config/candidates_v3/balanced_physics.json',
    'src/reserve_odometry/reserve_odometry/node.py',
    'src/reserve_odometry/reserve_odometry/timeline.py',
    'src/reserve_odometry/reserve_odometry/route.py']
SOURCE = UNCHANGED + [CORE, PROTOCOL, 'tools/research_h07/run.py',
                      'research/H07/test_actuator.py', '.github/workflows/research-h07.yml']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def hashes():
    return {p: ev.sha(ROOT / p) for p in SOURCE}


def verify_baseline_contract():
    for path in UNCHANGED:
        expected = hashlib.sha256(git('show', BASELINE + ':' + path)).hexdigest()
        if ev.sha(ROOT / path) != expected:
            raise AssertionError('Immutable baseline dependency changed: ' + path)
    return hashes()


def base_config():
    return json.loads((ROOT / PROFILE).read_text())['config']


def candidates():
    base = base_config()
    tau = base['actuator_tau_s']
    return {name: ex.Config(**(base | {'traction_tau_s': a*tau, 'braking_tau_s': b*tau}))
            for name, a, b in VARIANTS}


def provenance():
    return dict(hypothesis='H07', baseline_commit=BASELINE, baseline_profile=PROFILE,
                source_commit=git('rev-parse', 'HEAD').decode().strip(),
                source_sha256=verify_baseline_contract(),
                created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                python=platform.python_version(), numpy=np.__version__,
                run_id=os.environ.get('GITHUB_RUN_ID'),
                run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'), test_evaluated=False)


class TrainingStore(ex.Store):
    def __init__(self, journal):
        super().__init__()
        self.journal = journal

    def load(self, bag, purpose):
        if purpose != 'train':
            raise PermissionError('H07 identification is train-only')
        value = super().load(bag, purpose)
        ev.save(self.journal, dict(test_evaluated=False, access=self.access))
        print('TRAIN_LOADED', bag, flush=True)
        return value


def acceleration(config, u, v, dt=.1):
    """The v3 offline fitting discretization, with a command-dependent lag.

    This is not the runtime observer: v is wheel pseudo-ground-truth here,
    and the centered acceleration label lives only in training_set().
    """
    c = config
    q = np.clip((np.abs(u)-c.command_deadband)/(1-c.command_deadband), 0, 1)**c.command_exponent
    force = c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m/c.mass_kg
    power, brake = c.max_power_w/c.mass_kg, c.max_brake_force_n/c.mass_kg
    target = np.where(u >= 0, q*np.minimum(force, power/np.maximum(abs(v), 1.)),
                      -np.tanh(v/.2)*q*brake)
    tau = np.full(len(u), c.actuator_tau_s)
    if c.traction_tau_s > 0:
        tau[u > c.command_deadband] = c.traction_tau_s
    if c.braking_tau_s > 0:
        tau[u < -c.command_deadband] = c.braking_tau_s
    alpha = 1-np.exp(-dt/tau)
    drive = np.empty(len(u))
    state = 0.
    for i in range(len(u)):
        state = (1-alpha[i])*state + alpha[i]*target[i]
        drive[i] = state
    return drive - c.rolling_force_n/c.mass_kg*np.tanh(v/.2) - c.quadratic_drag_n_s2_m2/c.mass_kg*v*abs(v)


def fit(output):
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    meta = provenance()
    ev.save(output/'started.json', meta)
    store = TrainingStore(output/'access.json')
    training, stats = ex.training_set(store)  # unchanged train masks and seeded sampling
    group_n = Counter()
    for row in training:
        group_n[row['group']] += len(row['indices'])
    modes = np.concatenate([np.sign(b['u'][b['indices']]) for b in training])
    mode_n = Counter(modes)
    weights = np.concatenate([np.full(len(b['indices']), 1/math.sqrt(group_n[b['group']])) for b in training])
    weights /= np.sqrt(np.mean(weights*weights))
    weights *= np.array([math.sqrt(len(modes)/(len(mode_n)*mode_n[x])) for x in modes])
    models = {'baseline': ex.Config(**base_config()), **candidates()}
    results = {}
    for name, config in models.items():
        errors = [(acceleration(config, row['u'], row['v'])-row['a'])[row['indices']] for row in training]
        residual = np.concatenate(errors)*weights
        cost = .01*(np.sqrt(1+(residual/.1)**2)-1)
        per_bag, offset = [], 0
        for row, error in zip(training, errors):
            n = len(error)
            per_bag.append(dict(bag=row['bag'], group=row['group'], n=n,
                                acceleration_rmse=float(np.sqrt(np.mean(error**2))),
                                soft_l1_cost=float(np.sum(cost[offset:offset+n]))))
            offset += n
        results[name] = dict(config=asdict(config), soft_l1_cost=float(np.sum(cost)),
                             weighted_acceleration_rmse=float(np.sqrt(np.mean(residual**2))), per_bag=per_bag)
        ev.save(output/(name+'.json'), results[name])
        print('TRAIN_SCORE', name, results[name]['soft_l1_cost'], flush=True)
    # Ordered iteration resolves exact ties; baseline is a control, not a candidate.
    selected_name = min(candidates(), key=lambda name: results[name]['soft_l1_cost'])
    result = dict(**meta, variants=results, selected=selected_name, stats=stats,
                  selected_samples=sum(row['selected'] for row in stats),
                  mode_counts={str(k):v for k,v in mode_n.items()},
                  elapsed_s=time.perf_counter()-started)
    ev.save(output/'training.json', result)
    selected = dict(**meta, name=selected_name, config=results[selected_name]['config'],
                    selection_criterion='minimum train-only group/mode-weighted soft_l1 cost; six preregistered pairs',
                    train_gain=1-results[selected_name]['soft_l1_cost']/results['baseline']['soft_l1_cost'],
                    training_sha256=ev.sha(output/'training.json'),
                    access_sha256=ev.sha(output/'access.json'), validation_opened=False)
    ev.save(output/'selected.json', selected)
    text = 'reserve_odometry:\n  ros__parameters:\n    rate_hz: 20.0\n    alignment_delay_s: 0.0\n'
    text += '    front_scale: 0.2777777777777778\n    rear_scale: 0.2777777777777778\n'
    text += ''.join('    model.'+key+': '+str(value)+'\n' for key,value in selected['config'].items())
    (output/'selected.yaml').write_text(text)
    print('SELECTED_BEFORE_VALIDATION', selected_name, flush=True)


def verify_frozen(path, commit):
    path = path.resolve()
    relative = str(path.relative_to(ROOT))
    # The frozen profile must exist in a REAL git commit created before validation.
    if git('show', commit+':'+relative) != path.read_bytes():
        raise AssertionError('Selected profile is not exactly the committed freeze')
    selected = json.loads(path.read_text())
    if selected['baseline_commit'] != BASELINE or selected['validation_opened']:
        raise AssertionError('Wrong baseline or already contaminated selection')
    if selected['source_sha256'] != verify_baseline_contract():
        raise AssertionError('Code/evaluator/protocol changed after training freeze')
    if selected['config'] != asdict(candidates()[selected['name']]):
        raise AssertionError('Candidate is outside the preregistered grid')
    if ev.sha(path.parent/'training.json') != selected['training_sha256']:
        raise AssertionError('Training evidence changed')
    if ev.sha(path.parent/'access.json') != selected['access_sha256']:
        raise AssertionError('Training access evidence changed')
    return selected


def configure_worker(config):
    base = base_config()
    v4 = json.loads((ROOT/'src/reserve_odometry/config/candidates_v3/balanced_physics.json').read_text())['config']
    # Only configuration wiring is replaced; score/metrics/replay/fault generator are unchanged.
    common.configurations = lambda: {'baseline_v2': ex.Config(**v4),
                                     'balanced_physics': ex.Config(**base),
                                     'H07': ex.Config(**config)}


def transition_mask(events, t):
    commands = events[events[:,1] == 0][:, [0,2]]
    commands = commands[np.argsort(commands[:,0], kind='stable')]
    if not len(commands):
        return np.zeros(len(t), bool)
    _, indices = np.unique(commands[:,0], return_index=True)
    commands = commands[indices]
    valid = np.isfinite(commands).all(axis=1) & (np.abs(commands[:,1]) <= 1.000001)
    commands = commands[valid]
    if len(commands) < 2:
        return np.zeros(len(t), bool)
    deadband = base_config()['command_deadband']
    modes = np.where(commands[:,1] > deadband, 1, np.where(commands[:,1] < -deadband, -1, 0))
    changes = commands[1:,0][modes[1:] != modes[:-1]]
    if not len(changes):
        return np.zeros(len(t), bool)
    j = np.searchsorted(changes, t, side='right')-1
    age = t-changes[np.maximum(j, 0)]
    return (j >= 0) & (age >= 0) & (age < 2.)


def validate_bag(bag):
    clean, stress, access = common.validate_bag(bag)
    # Descriptive post-selection diagnostics. A second identical validation read
    # is recorded explicitly; no diagnostic feeds back into candidate selection.
    store = ex.Store()
    events, refs = store.load(bag, 'validation')
    models = common.configurations()
    ops = dict(rate_hz=20., alignment_delay_s=0.)
    pred = {name: ev.replay(events, models[key], ops)[0]
            for name,key in [('v5_adaptive_05s','balanced_physics'), ('H07','H07')]}
    a = pred['v5_adaptive_05s']
    diag = dict(bag=bag, group=store.records[bag]['group'], receivers={})
    if len(a):
        if not np.array_equal(a[:,0], pred['H07'][:,0]):
            raise AssertionError('Transition diagnostic timestamps differ')
        mask = transition_mask(events, a[:,0])
        for receiver, ref in refs.items():
            target = ex.match(ref, a[:,0])
            diag['receivers'][receiver] = {name: ex.metrics(a[:,0], p[:,1], target, mask)
                                            for name,p in pred.items()}
    return clean, stress, access+store.access, diag


def validate(output, frozen, freeze_commit, workers):
    selected = verify_frozen(frozen, freeze_commit)  # before any validation Store.load
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    meta = provenance() | {'freeze_commit': freeze_commit, 'freeze_sha256': ev.sha(frozen),
                           'candidate_name': selected['name']}
    ev.save(output/'started.json', meta)
    plan = ex.Store().plan
    clean, stress, access, diagnostics = [], [], [], []
    with ProcessPoolExecutor(max_workers=workers, initializer=configure_worker, initargs=(selected['config'],)) as pool:
        for c, faults, journal, diag in pool.map(validate_bag, plan['splits']['validation']):
            clean.append(c); stress.extend(faults); access.extend(journal); diagnostics.append(diag)
            ev.save(output/'bags'/(c['bag']+'.json'), dict(clean=c, stress=faults, transitions=diag))
            ev.save(output/'access.json', dict(test_evaluated=False, access=access))
            print('VALIDATION_CHECKPOINT', c['bag'], flush=True)
    reproduction = common.reproduce_published_v5(clean)
    decision = common.decide(clean, stress, ['v4_default','v5_adaptive_05s','H07'])
    base, candidate = decision['candidates']['v5_adaptive_05s'], decision['candidates']['H07']
    additional = []
    if candidate['pooled_rmse'] > base['pooled_rmse']*1.005:
        additional.append('pooled_rmse_regression_over_0.5_percent')
    for row in stress:
        for receiver, scores in row['receivers'].items():
            b, c = scores['v5_adaptive_05s'], scores['H07']
            if b.get('recovery_s') is not None and c.get('recovery_s') is None:
                additional.append('new_unrecovered:'+row['bag']+'/'+receiver+'/'+str(row['fault']))
    passed = candidate['eligible'] and not additional
    result = dict(**meta, models={'v5_adaptive_05s':asdict(ex.Config(**base_config())), 'H07':selected['config']},
                  clean=clean, stress=stress, baseline_reproduction=reproduction,
                  transitions=diagnostics, elapsed_s=time.perf_counter()-started)
    ev.save(output/'results.json', result)
    ev.save(output/'v6_decision.json', decision)  # exact result of unchanged historical gate
    verdict = dict(hypothesis='H07', candidate_name=selected['name'],
                   conclusion='confirmed_on_reused_validation' if passed else 'rejected',
                   ready_to_merge=False, runtime_certified=False, test_evaluated=False,
                   baseline_reproduction=reproduction,
                   baseline=base, candidate=candidate,
                   additional_contract_rejections=additional,
                   transitions={name:common.macro(diagnostics,name,'rmse') for name in ('v5_adaptive_05s','H07')},
                   fault_types={kind:{name:common.macro([r for r in stress if r['fault']['kind']==kind],name,'event_rmse')
                                       for name in ('v5_adaptive_05s','H07')} for kind in ('bias','dropout','lock')},
                   limitations=['reused validation, NOT independent final-test evidence',
                                'wheel-only train pseudo-label and coarse six-pair grid',
                                'offline replay is NOT a ROS latency/resource benchmark',
                                'scalar distance is NOT xyz or full terminal drift'])
    ev.save(output/'decision.json', verdict)
    # Tidy raw per-bag/receiver comparison; full nested metrics remain in results.json.
    import csv
    columns = ['bag','group','receiver','scenario','fault_start','fault_end','baseline_rmse','candidate_rmse',
               'baseline_n','candidate_n','baseline_distance_rmse','candidate_distance_rmse',
               'baseline_false_stops','candidate_false_stops','baseline_recovery_s','candidate_recovery_s']
    with (output/'per_bag.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns); writer.writeheader()
        for row in clean+stress:
            fault = row.get('fault', {})
            for receiver,scores in row['receivers'].items():
                b,c = scores['v5_adaptive_05s'],scores['H07']
                metric = 'event_rmse' if fault else 'rmse'
                writer.writerow(dict(bag=row['bag'],group=row['group'],receiver=receiver,
                    scenario=fault.get('kind','clean'),fault_start=fault.get('start'),fault_end=fault.get('end'),
                    baseline_rmse=b.get(metric),candidate_rmse=c.get(metric),baseline_n=b['n'],candidate_n=c['n'],
                    baseline_distance_rmse=common.metric_value(b,'distance'),candidate_distance_rmse=common.metric_value(c,'distance'),
                    baseline_false_stops=b['false_stop_samples'],candidate_false_stops=c['false_stop_samples'],
                    baseline_recovery_s=b.get('recovery_s'),candidate_recovery_s=c.get('recovery_s')))
    print(json.dumps(verdict, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['train','validate'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frozen', type=Path)
    parser.add_argument('--freeze-commit')
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error('workers must be 1..8')
    if args.stage == 'train':
        fit(args.output)
    else:
        if args.frozen is None or not args.freeze_commit:
            parser.error('validation requires --frozen and --freeze-commit')
        validate(args.output, args.frozen, args.freeze_commit, args.workers)


if __name__ == '__main__':
    main()
