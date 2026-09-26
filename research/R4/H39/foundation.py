"""R4-H39 fixed train-only lattice prerequisite. This is NOT a runtime observer."""
import argparse
from collections import Counter
import csv
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import subprocess
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'tools/research_v3'), str(ROOT/'tools')]
import experiment as ex
from stage import sha, save

QMIN, QMAX = 1e-6, .5
QPRACTICAL = math.sqrt(.0012)
REGIMES = ('traction', 'coast', 'brake')


def take(a, n):
    return a[np.linspace(0, len(a)-1, min(n, len(a)), dtype=int)] if len(a) else a


def verify_sources():
    receipt_path = ROOT/'research/R4/H39/SOURCE_RECEIPT.json'
    if not receipt_path.exists():
        baseline = 'e3b0c9c039d2953fbfcda51231263d38ef9f1024'
        tree = subprocess.check_output(['git','rev-parse',baseline+'^{tree}'],cwd=ROOT,text=True).strip()
        if tree != 'eae49a504bc59b5c9b408445150bef32e111956f':
            raise ValueError('Remote baseline tree mismatch')
        entries = subprocess.check_output(['git','ls-tree','-rz',baseline],cwd=ROOT).split(b'\0')
        files = []
        for entry in entries:
            if not entry: continue
            meta, path = entry.split(b'\t',1)
            mode, kind, expected = meta.split()
            if kind != b'blob': raise ValueError('Unexpected non-blob')
            path = path.decode(); payload = (ROOT/path).read_bytes()
            actual = hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
            actual_mode = '100755' if (ROOT/path).stat().st_mode & 0o111 else '100644'
            if actual != expected.decode() or actual_mode != mode.decode():
                raise ValueError('Remote source bytes/mode mismatch: '+path)
            files.append({'path':path,'sha256':sha(ROOT/path),'mode':actual_mode})
        if len(files) != 301: raise ValueError('Remote baseline file count')
        save(receipt_path, {'source_status':'VERIFIED','baseline_commit_binding':baseline,
            'actual_git_tree':tree,'file_count':len(files),'files':files,
            'zip_sha256':'a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2',
            'verification_scope':'All baseline Git object paths/bytes/modes. ZIP hash refers to separately verified user archive; ZIP not downloaded in Actions.'})
    receipt = json.loads(receipt_path.read_text())
    if receipt['actual_git_tree'] != 'eae49a504bc59b5c9b408445150bef32e111956f':
        raise ValueError('Wrong source tree')
    for f in receipt['files']:
        if sha(ROOT/f['path']) != f['sha256']:
            raise ValueError('Baseline source modified: '+f['path'])
    return receipt


def collect(events):
    """Rows t, SI velocity, regime; only backward/arrived command and unique stamps."""
    prev = [None, None]
    command = None
    arrays = [[], []]
    counts = [Counter(), Counter()]
    for t, ch, value in events:
        ch = int(ch)
        if ch == 0:
            if command is None or t > command[0]:
                command = (t, value)
            continue
        i = ch-1
        counts[i]['all_rows'] += 1
        old = prev[i]
        if old is not None and t <= old[0]:
            counts[i]['duplicate_or_old_stamp'] += 1
            continue
        counts[i]['new_stamp'] += 1
        prev[i] = (t, value)
        if old is not None and value == old[1]:
            counts[i]['new_stamp_unchanged_value'] += 1
        if not math.isfinite(value) or not .1 <= abs(value) <= 40:
            counts[i]['range_or_near_zero'] += 1
            continue
        if (old is None or not 0 < t-old[0] <= .25 or
                abs(value-old[1]) <= 1e-9):
            counts[i]['no_changing_predecessor'] += 1
            continue
        if (command is None or not 0 <= t-command[0] <= .5 or
                not math.isfinite(command[1]) or abs(command[1]) > 1):
            counts[i]['command_unavailable'] += 1
            continue
        u = command[1]
        regime = 0 if u > .04 else (2 if u < -.04 else 1)
        arrays[i].append((t, value, regime))
        counts[i]['eligible'] += 1
    return [np.asarray(a, float).reshape(-1, 3) for a in arrays], [dict(c) for c in counts]


def qualify(a):
    v = a[:, 1]
    return len(v) >= 1000 and len(np.unique(v)) >= 100 and np.ptp(v) >= 1


def proposals(groups):
    gaps = []
    for a in groups.values():
        g = np.diff(np.unique(a[:, 1]))
        gaps.append(g[g > 0])
    g = np.concatenate(gaps) if gaps else np.array([])
    pool = set()
    if len(g):
        rounded = np.array([float(format(x, '.10g')) for x in g])
        values, counts = np.unique(rounded, return_counts=True)
        mode = values[np.lexsort((values, -counts))[:64]]
        seeds = np.r_[mode, np.quantile(g, np.linspace(0, 1, 101))]
        for x in seeds:
            for n in range(1, 33):
                if QMIN <= x/n <= QMAX:
                    pool.add(float(x/n))
    for k in range(-6, 1):
        for m in (1, 2, 2.5, 5):
            for scale in (1., 3.6):
                q = m*10**k/scale
                if QMIN <= q <= QMAX:
                    pool.add(q)
    return take(np.array(sorted(pool)), 8192)


def distance(v, q, shift):
    x = (v-shift)/q
    return np.abs(x-np.rint(x))*q


def inliers(v, q, shift):
    return distance(v, q, shift) <= max(1e-10, .001*q)


def refine(q, groups):
    pieces = [take(a[:, 1], 2048) for a in groups.values()]
    values = np.concatenate(pieces)
    weight = np.concatenate([np.full(len(v), 1./len(v)) for v in pieces])
    phase = np.sum(weight*np.exp(2j*np.pi*values/q))/weight.sum()
    coherence = abs(phase)
    if coherence < .975:
        return None
    shift = (np.angle(phase)/(2*np.pi)*q) % q
    for _ in range(3):
        ix = np.rint((values-shift)/q)
        ok = np.abs(values-shift-q*ix) <= .02*q
        if ok.sum() < 100:
            return None
        x, y, w = ix[ok], values[ok], weight[ok]
        xm, ym = np.average(x, weights=w), np.average(y, weights=w)
        den = np.sum(w*(x-xm)**2)
        if den <= 0:
            return None
        q = float(np.sum(w*(x-xm)*(y-ym))/den)
        if not QMIN <= q <= QMAX:
            return None
        shift = float((ym-q*xm) % q)
    return q, shift, float(coherence)


def evaluate_grid(groups, q, shift):
    stats, regimes = {}, {}
    for group, a in groups.items():
        good = inliers(a[:, 1], q, shift)
        stats[group] = {'samples': len(a), 'fraction': float(good.mean()),
            'residual_p99_mps': float(np.quantile(distance(a[:, 1], q, shift), .99)),
            'levels': len(np.unique(np.rint((a[:, 1]-shift)/q))),
            'regimes': {name: {'n': int((a[:, 2] == j).sum()),
                'fraction': float(good[a[:, 2] == j].mean()) if np.any(a[:, 2] == j) else None}
                for j, name in enumerate(REGIMES)}}
    fractions = [s['fraction'] for s in stats.values()]
    for name in REGIMES:
        members = [s['regimes'][name] for s in stats.values() if s['regimes'][name]['n'] >= 300]
        regimes[name] = {'groups': len(members), 'samples': sum(s['n'] for s in members),
            'group_mean_fraction': float(np.mean([s['fraction'] for s in members])) if members else None,
            'passed': len(members) >= 3 and all(s['fraction'] >= .99 for s in members)}
    passed = (bool(fractions) and np.mean(fractions) >= .99 and
              np.mean(np.array(fractions) >= .99) >= .8 and all(s['passed'] for s in regimes.values()))
    return {'passed': bool(passed), 'group_mean_fraction': float(np.mean(fractions)) if fractions else None,
        'group_pass_fraction': float(np.mean(np.array(fractions) >= .99)) if fractions else None,
        'per_group': stats, 'regimes': regimes}


def fit_grid(groups):
    if not groups:
        return None, {'proposals': 0, 'coherent': 0, 'trials': []}
    qs = proposals(groups)
    trials, good = [], []
    for q in qs:
        candidate = refine(float(q), groups)
        if candidate is None:
            continue
        fitted, shift, coherence = candidate
        result = evaluate_grid(groups, fitted, shift)
        trials.append({'proposal_q': float(q), 'q': fitted, 'shift': shift, 'coherence': coherence,
            'fit_fraction': result['group_mean_fraction'], 'passed': result['passed']})
        if result['passed']:
            good.append((fitted, shift, result))
    selected = max(good, key=lambda r: r[0]) if good else None
    return selected, {'proposals': len(qs), 'coherent': len(trials), 'trials': trials}


def continuous_pair_bound(deltas, lo=QPRACTICAL, hi=QMAX):
    """Exact interval sweep over continuous q. A necessary condition, not a fitted grid."""
    d = np.abs(np.asarray(deltas, float))
    if not len(d):
        return {'pairs': 0, 'max_fraction': None, 'q_at_max': None}
    alpha, eps = .002, 2e-10
    endpoints = []
    for value in d:
        # n=0 includes tiny differences; n>0 intervals are pairwise disjoint here.
        for n in range(int(math.ceil((value+eps)/lo+alpha))+1):
            left = (value-eps)/alpha if n == 0 else (value-eps)/(n+alpha)
            right = hi if n == 0 else (value+eps)/(n-alpha)
            left, right = max(lo, np.nextafter(left, -np.inf)), min(hi, np.nextafter(right, np.inf))
            if left <= right:
                endpoints.append((float(left), -1))  # start before end at same value
                endpoints.append((float(right), 1))
    count = maximum = 0
    at = lo
    for q, sign in sorted(endpoints):
        count -= sign
        if count > maximum:
            maximum, at = count, q
    if maximum > len(d):
        raise AssertionError('Overlapping intervals double-counted a pair')
    return {'pairs': len(d), 'max_fraction': maximum/len(d), 'max_pairs': maximum,
        'q_at_max': at, 'range_mps': [lo, hi]}


def run(data_root, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    receipt = verify_sources()
    started = time.perf_counter()
    store = ex.Store(data_root)
    records = store.records
    groups = sorted({r['group'] for r in records.values() if r['split'] == 'train'})
    roles = {g: ('check' if i % 3 == 2 else 'fitting') for i, g in enumerate(groups)}
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT/'research/R4/H39').glob('*')) if p.is_file()}
    save(output/'started.json', {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source_status': receipt['source_status'], 'baseline_sha': receipt['baseline_commit_binding'],
        'baseline_tree': receipt['actual_git_tree'], 'source_sha256': source_hashes,
        'diagnostic_source_sha': os.environ.get('GITHUB_SHA'), 'candidate_sha': None,
        'python': platform.python_version(), 'numpy': np.__version__, 'group_roles': roles,
        'loader_file': ex.__file__, 'train_topics': list(ex.CHANNELS), 'train_gnss': False,
        'validation_opened': False, 'test_opened': False})
    all_arrays, group_arrays, group_pairs, per_bag, seen = {}, [{}, {}], [{}, {}], [], set()
    for bag in store.plan['splits']['train']:
        events, refs = store.load(bag, 'train')
        if any(refs.values()):
            raise AssertionError('Train references must be empty')
        arrays, counts = collect(events)
        r = records[bag]
        key = (r['group'], r['vehicle_wire_sha256'])
        duplicate = key in seen
        seen.add(key)
        per_bag.append({'bag': bag, 'group': r['group'], 'role': roles[r['group']],
            'duplicate_wire': duplicate, 'event_count': len(events), 'channels': counts,
            'sha256': r['sha256'], 'vehicle_wire_sha256': r['vehicle_wire_sha256']})
        for i, a in enumerate(arrays):
            all_arrays[bag+('_front' if i == 0 else '_rear')] = a
            if not duplicate:
                group_arrays[i].setdefault(r['group'], []).append(a)
                n = len(a)//2*2
                group_pairs[i].setdefault(r['group'], []).append(np.abs(a[:n:2,1]-a[1:n:2,1]))
        save(output/'access.json', store.access)
        print('TRAIN', bag, [len(a) for a in arrays], 'duplicate', duplicate, flush=True)
    np.savez_compressed(output/'eligible_train.npz', **all_arrays)
    save(output/'per_bag.json', per_bag)
    channels = {}
    for i, name in enumerate(('front','rear')):
        rows = {g: np.concatenate(group_arrays[i].get(g, [np.empty((0,3))])) for g in groups}
        qualified = {g:a for g,a in rows.items() if qualify(a)}
        fitting = {g:a for g,a in qualified.items() if roles[g] == 'fitting'}
        check = {g:a for g,a in qualified.items() if roles[g] == 'check'}
        selected, audit = fit_grid(fitting)
        save(output/(name+'_fitting_search.json'), audit)
        # Commit-like local stage receipt: check cannot alter this fit-only choice.
        calibration = {'q_mps': selected[0], 'shift_mps': selected[1]} if selected else None
        save(output/(name+'_FIT_LOCK.json'), {'selected': calibration, 'check_used_for_fit': False})
        check_result = evaluate_grid(check, selected[0], selected[1]) if selected else None
        group_stats = {}
        for g,a in rows.items():
            pairs = np.concatenate(group_pairs[i].get(g, [np.empty(0)]))
            bound = continuous_pair_bound(take(pairs,512))
            values = a[:,1]
            gaps = np.diff(np.unique(values))
            group_stats[g] = {'role': roles[g], 'eligible': len(a), 'qualified': g in qualified,
                'distinct_values': len(np.unique(values)), 'span_mps': float(np.ptp(values)) if len(a) else None,
                'gap_quantiles_mps': np.quantile(gaps,[0,.1,.5,.9,1]).tolist() if len(gaps) else None,
                'regime_counts': {r: int((a[:,2]==j).sum()) for j,r in enumerate(REGIMES)},
                'practical_pair_upper_bound': bound}
        reasons = []
        coverage = len(fitting)>=8 and len(check)>=4
        if not coverage: reasons.append('INSUFFICIENT_GROUP_COVERAGE')
        if selected is None: reasons.append('LATTICE_NOT_ESTABLISHED')
        if selected and not check_result['passed']: reasons.append('LATTICE_CHECK_FAILED')
        ratio = selected[0]**2/.12 if selected else None
        if ratio is not None and ratio < .01: reasons.append('NO_PRACTICAL_SIGNAL')
        for role in ('fitting','check'):
            fractions = [group_stats[g]['practical_pair_upper_bound']['max_fraction']
                for g in qualified if roles[g] == role]
            if not fractions or np.mean(np.array(fractions)>=.98)<.8:
                reasons.append('NO_PRACTICAL_LATTICE_PAIR_SUPPORT:'+role)
        channels[name] = {'qualified_fit_groups': len(fitting), 'qualified_check_groups': len(check),
            'selected': calibration, 'quantization_variance_ratio': ratio,
            'fitting': selected[2] if selected else None, 'check': check_result,
            'per_group': group_stats, 'reasons': reasons, 'foundation_passed': not reasons,
            'proposals_evaluated': audit['proposals'], 'coherent_proposals': audit['coherent']}
        save(output/(name+'_RESULT.json'), channels[name])
    passed = all(c['foundation_passed'] for c in channels.values())
    summary = {'round':'R4','hypothesis_id':'R4-H39','baseline_sha':receipt['baseline_commit_binding'],
        'baseline_tree':receipt['actual_git_tree'],'zip_sha256':receipt['zip_sha256'],
        'source_status':'VERIFIED','data_status':'AVAILABLE','execution_status':'COMPLETED',
        'publication_status':'CHECKPOINT_PENDING','mechanism_status':'FOUNDATION_ONLY_NO_RUNTIME_CANDIDATE',
        'coverage_status': {k:[v['qualified_fit_groups'],v['qualified_check_groups']] for k,v in channels.items()},
        'scientific_verdict':'NOT_EVALUATED' if passed else 'INCONCLUSIVE',
        'foundation_passed':passed,'accuracy_contract_evaluated':False,'accuracy_contract_passed':False,
        'candidate_implemented':False,'measured_source_sha':None,'diagnostic_source_sha':os.environ.get('GITHUB_SHA'),
        'report_sha':None,'freeze_sha':None,'validation_opened':False,'test_opened':False,
        'enabled_runtime_verified':False,'ready_to_merge':False,'variants_tested':0,
        'train_bags':len(per_bag),'train_groups':len(groups),'unique_wire_streams':len(seen),
        'run_ids':[os.environ.get('GITHUB_RUN_ID','local')], 'channels':channels,
        'rejection_reasons':[], 'prerequisite_reasons':{k:v['reasons'] for k,v in channels.items()},
        'missing_evidence':['candidate accuracy and enabled runtime are not evaluated'],
        'next_resume_step':'one-step posterior effect prerequisite' if passed else 'No runtime candidate under this preregistered protocol; report foundation outcome.',
        'elapsed_wall_s':time.perf_counter()-started}
    save(output/'SUMMARY.json',summary)
    with (output/'per_group.csv').open('w',newline='') as f:
        fields=['channel','group','role','eligible','qualified','distinct_values','span_mps','pair_count','best_practical_pair_fraction']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for name,ch in channels.items():
            for group,row in ch['per_group'].items():
                w.writerow(dict(channel=name,group=group,**{k:row[k] for k in fields[2:7]},
                    pair_count=row['practical_pair_upper_bound']['pairs'],
                    best_practical_pair_fraction=row['practical_pair_upper_bound']['max_fraction']))
    save(output/'HASHES.json',{p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file() and p.name!='HASHES.json'})
    print('VERDICT',summary['scientific_verdict'],summary['prerequisite_reasons'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run(args.data_root,args.output)
