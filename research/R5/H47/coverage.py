#!/usr/bin/env python3
"""H47 foundation only: immutable inputs -> paired passive replay -> offline labels.

There is deliberately no model fitting, threshold selection, injection, reference
scorer, or validation/development/test command in this module.
"""
from __future__ import annotations
import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import csv
from dataclasses import asdict
import hashlib
import io
from itertools import zip_longest
import json
import math
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
import time
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'src/reserve_odometry'), str(ROOT / 'tools')]
import numpy as np
from export_bags import decode
from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.timeline import Timeline
from features import CausalFeatureProbe, FEATURE_NAMES
from offline_labels import TeacherPoint, unique_nearest, proxy_pair_labels

BASE = 'b2783206000091ab11a1c11ac3ff79082188a4fb'
TREE = '973d50d288e050325ee1c71a90fa8d81f2a099af'
DATA = 'd0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52'
SPLIT = '20928a29daad2b4178ddb92e2a4d9ddb347952f6c03845802a8d82fff7da5ae0'
FOLDS = '7efb88def952af5089e89c0415256b529bf6e944cda8596387569cc055192356'
TEACHER = '5c8129133758bbb715f2e170122b976f95d0240c18daa731472d910f0bf274d0'
ATLAS = '73d3269f012f25f4c46787369bdb85fc218fbf149d29cd60c63eb8f20687bd5c'
TOPICS = {'/vehicle/driver_position_cmd': (0, 'tram_vehicle_msgs/msg/DriverControllerCommand'),
          '/vehicle/front_bogie_velocity': (1, 'tram_vehicle_msgs/msg/VelocitySensor'),
          '/vehicle/rear_bogie_velocity': (2, 'tram_vehicle_msgs/msg/VelocitySensor')}
REASONS = ('READY', 'INITIAL_OR_STOP', 'NO_NEW_FRESH_SAMPLE', 'NATIVE_OR_INPUT_GATE',
           'DIRECTION_OR_LOW_SPEED', 'RATE_HISTORY_MISSING', 'PRIOR_HISTORY_MISSING', 'OUT_OF_DOMAIN')
LABEL_REASONS = ('FEATURES_NOT_READY', 'TEACHER_MISSING_OR_AMBIGUOUS', 'LOW_SPEED',
                 'INTERMEDIATE_OR_COMMON_PROXY', 'CLEAN_PAIR', 'FRONT_FAULT', 'REAR_FAULT')


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n')


def checked_json(path, expected):
    if sha(path) != expected:
        raise ValueError('Hash mismatch: ' + str(path))
    return json.loads(Path(path).read_text(encoding='utf-8'))


def safe_train_record(record):
    # Must run before opening, hashing, or resolving any measurement file.
    if record.get('split') != 'train' or record.get('fold') not in ('fit', 'check'):
        raise PermissionError('Only frozen original train fit/check may be read')
    bag = record.get('bag', '')
    if not bag or '/' in bag or '\\' in bag or '..' in bag:
        raise ValueError('Unsafe bag identity')


def profile():
    d = json.loads((ROOT/'src/reserve_odometry/config/champion_v8.json').read_text())
    return Config(**d['config']), ReadoutConfig(**d['readout'])


def representatives(records):
    """Choose by immutable metadata, before labels; never choose best reference."""
    result = {}
    for r in sorted(records, key=lambda x: x['bag']):
        safe_train_record(r)
        key = r['wire_sha256']
        if key in result:
            old = result[key]
            if (old['fold'], old['group']) != (r['fold'], r['group']):
                raise ValueError('Wire identity crosses a source group or fold')
        else:
            result[key] = r
    return {r['bag']: result[r['wire_sha256']]['bag'] for r in records}


def episode_onsets(times):
    """A >1s gap without a faulty update starts a new episode; no tick inflation."""
    values = sorted(set(float(t) for t in times))
    if not all(math.isfinite(t) for t in values):
        raise ValueError('Nonfinite episode time')
    return [t for i, t in enumerate(values) if i == 0 or t - values[i-1] > 1.0]


def qualifies_group(fault_updates, clean_updates, max_episodes_same_bag):
    return fault_updates >= 10 and clean_updates >= 100 and max_episodes_same_bag >= 2


def prepare(args):
    out = Path(args.output)
    if out.exists() or Path(args.data_root).exists():
        raise FileExistsError('Use a new dependency lock and a new data-root')
    receipts, launch = Path(args.receipts), Path(args.launch)
    sr = json.loads((receipts/'SOURCE_RECEIPT.json').read_text())
    if (sr['actual_git_tree'], sr['file_count']) != (TREE, 320):
        raise ValueError('Full baseline receipt mismatch')
    if sha(args.source_zip) != sr['zip_sha256']:
        raise ValueError('Source ZIP differs from receipt')
    # Bind the actual canonical source files, not just the receipt.
    source_files = {}
    for x in sr['files']:
        p = ROOT/x['path']
        if sha(p) != x['sha256'] or ('100755' if p.stat().st_mode & 0o111 else '100644') != x['mode']:
            raise ValueError('Canonical source differs: ' + x['path'])
        source_files[x['path']] = x['sha256']
    for p in HERE.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:
            source_files[str(p.relative_to(ROOT))] = sha(p)
    transport = json.loads((receipts/'components.transport.json').read_text())
    tn = json.loads((receipts/'teacher.native.lock.json').read_text())
    an = json.loads((receipts/'atlas.native.lock.json').read_text())
    bridge = json.loads((receipts/'folds.bridge.json').read_text())
    if transport['status'] != 'TRANSPORT_VERIFIED' or tn['handoff_sha256'] != TEACHER or an['handoff_sha256'] != ATLAS:
        raise ValueError('Native/transport receipt identities differ')
    if not an['verified'] or len(tn['files']) != 85 or len(an['artifacts']) != 53:
        raise ValueError('Incomplete native verification')
    if bridge['status'] != 'SEMANTIC_FOLD_EQUIVALENCE_VERIFIED' or bridge['records'] != 64:
        raise ValueError('Missing actual folds bridge')
    for kind, root, entries, expected in (
        ('teacher', Path(args.teacher_root), tn['files'], TEACHER),
        ('atlas', Path(args.atlas_root), an['artifacts'], ATLAS)):
        handoff = checked_json(root/'R5_HANDOFF.json', expected)
        if handoff['baseline_sha'] != BASE or handoff['baseline_tree'] != TREE or handoff['dataset_sha256'] != DATA:
            raise ValueError('Upstream baseline/data mismatch')
        for x in entries:
            p = root/x['path']
            if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
                raise ValueError('Invalid dependency path')
            if sha(p) != x['sha256'] or p.stat().st_size != x['bytes']:
                raise ValueError('Changed upstream file: ' + x['path'])
    td = checked_json(Path(args.teacher_root)/'R5_HANDOFF.json', TEACHER)
    split = checked_json(ROOT/'research/split_v3.json', SPLIT)
    folds = checked_json(launch/'contracts/TRAIN_FOLDS.json', FOLDS)
    rs = {r['bag']: r for r in split['records']}
    ts = {r['bag']: r for r in td['files'] if r.get('kind') == 'teacher_array'}
    records = []
    for f in folds['records']:
        r = dict(rs[f['bag']], fold=f['fold'], wire_sha256=f['wire_sha256'], teacher=ts[f['bag']])
        safe_train_record(r)
        if r['group'] != f['group'] or r['vehicle_wire_sha256'] != f['wire_sha256']:
            raise ValueError('Canonical fold/wire mismatch')
        if r['sha256'] != r['teacher']['db_sha256'] or (r['group'], r['fold']) != (r['teacher']['group'], r['teacher']['fold']):
            raise ValueError('Teacher source mismatch')
        records.append(r)
    if len(records) != 64 or len({r['group'] for r in records}) != 27:
        raise ValueError('Incomplete train membership')
    reps = representatives(records)
    dataset = Path(args.dataset_zip)
    if sha(dataset) != DATA or dataset.stat().st_size != 256294592:
        raise ValueError('Pinned dataset mismatch')
    root = Path(args.data_root); root.mkdir(parents=True)
    inner = root/'data.zip'
    with zipfile.ZipFile(dataset) as z:
        if z.namelist().count('data.zip') != 1:
            raise ValueError('Missing/duplicate data.zip')
        with z.open('data.zip') as src, inner.open('xb') as dst:
            shutil.copyfileobj(src, dst)
    extracted = []
    with zipfile.ZipFile(inner) as z:
        names = Counter(z.namelist())
        for r in records:
            safe_train_record(r)
            name = r['bag']+'/'+r['bag']+'_0.db3'
            if names[name] != 1:
                raise ValueError('Missing/duplicate permitted DB')
            value = z.read(name)  # only original train DBs, CRC checked by ZipFile
            if hashlib.sha256(value).hexdigest() != r['sha256'] or len(value) != r['bytes']:
                raise ValueError('Permitted DB identity mismatch')
            p = root/name; p.parent.mkdir(parents=True)
            with p.open('xb') as fh: fh.write(value)
            extracted.append(dict(bag=r['bag'], fold=r['fold'], sha256=r['sha256'], bytes=len(value)))
    lock = dict(schema_version=1, hypothesis_id='R5-H47', baseline_sha=BASE, baseline_tree=TREE,
        status='DEPENDENCIES_VERIFIED', coverage_authorized=True, fitting_authorized=False,
        plan_sha='49fd44ffd5216526c757b2c9b8eb04a88b07ddce',
        resumed_from='5715837a035bb43eff00de719b84f3b3e231ebdd',
        teacher_source_sha=td['measured_source_sha'], teacher_handoff_sha256=TEACHER,
        atlas_source_sha='2e3268714bf229e3a0292ca69b8102f7bddde832', atlas_handoff_sha256=ATLAS,
        teacher_policy_sha256=td['teacher_policy_sha256'], reference_contract_sha256=td['reference_contract_sha256'],
        dataset_sha256=DATA, split_sha256=SPLIT, folds_sha256=FOLDS,
        source_zip_sha256=sr['zip_sha256'], source_files=source_files,
        preflight_receipts={p.name:sha(p) for p in receipts.glob('*.json')},
        native_files_verified=dict(teacher=85, atlas=53), actual_fold_bridge=bridge,
        records=records, representatives=reps, extracted=extracted,
        drive=dict(workspace='18B6ZRMpKUzZ8A9GYYEx38Vt0vsNMDfSz',
                   source='1yRQp9K9PrabA5KbUHJ6Pk4WBTI9UT9eC',
                   dataset_folder='1GwDWP2JbAWnDmq2Mh1fwIcHoiQbixttg',
                   dataset_parts_manifest='1-C1zcTGeMyLckQwuI5LVLRkxKF38NevZ',
                   teacher='1IMOfUjzBYtkhxSflKd39jhjMH5KPYOt1',
                   atlas='1MyidYX4Dqyueznm8ik81hQJ8MTMas2IF',
                   launch='1suagMTf5Sf4_oQA2G2KmnFh-hBQmVCqV'),
        sqlite_opened=False, validation_extracted=False, development_extracted=False, test_extracted=False)
    save(out, lock)
    print(json.dumps(dict(status=lock['status'], train_bags=len(records), unique_wire_streams=len(set(reps.values())), lock_sha256=sha(out))))


def load_vehicle_events(record, root, journal):
    safe_train_record(record)
    p = Path(root)/record['bag']/(record['bag']+'_0.db3')
    if sha(p) != record['sha256']:
        raise ValueError('DB changed before SQLite')
    journal.write(json.dumps(dict(event='SQL_OPEN', bag=record['bag'], split='train', fold=record['fold'],
                                  topics=list(TOPICS), db_sha256=record['sha256']))+'\n'); journal.flush()
    counts = Counter(); wire = hashlib.sha256(); events = []
    con = sqlite3.connect(p.resolve().as_uri()+'?mode=ro&immutable=1', uri=True)
    try:
        con.execute('PRAGMA query_only=ON')
        query = ('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                 'WHERE t.name IN (?,?,?) ORDER BY m.timestamp,m.id')
        for topic, typ, raw in con.execute(query, list(TOPICS)):
            ch, expected = TOPICS[topic]
            if typ != expected: raise ValueError('Unexpected vehicle CDR type')
            stamp, values = decode(raw, typ)
            wire.update(topic.encode()+b'\0'+raw[12:])
            events.append(((stamp-record['sensor_start_ns'])/1e9, ch, float(values[0])/(15 if ch==0 else 3.6)))
            counts[topic] += 1
    finally:
        con.close()
    if wire.hexdigest() != record['wire_sha256'] or any(counts[t] != record['counts'].get(t, 0) for t in TOPICS):
        raise ValueError('Vehicle count/wire fingerprint differs from canonical metadata')
    journal.write(json.dumps(dict(event='SQL_CLOSE', bag=record['bag'], rows=len(events), wire_sha256=wire.hexdigest()))+'\n');journal.flush()
    return events


class IndexedTeacher:
    """Offline index only; calls the unchanged pure matcher on a bounded slice."""
    def __init__(self, points):
        self.points = sorted((p for p in points if p.accepted and math.isfinite(p.t)
                              and math.isfinite(p.speed_magnitude) and p.speed_magnitude >= 0), key=lambda p:p.t)
        self.times = [p.t for p in self.points]
    def nearest(self, t):
        if not math.isfinite(t): return None
        a, b = bisect_left(self.times, t-.05), bisect_right(self.times, t+.05)
        return unique_nearest(self.points[a:b], t)


def load_teacher(record, root, journal):
    safe_train_record(record)
    r = record['teacher']; p = Path(root)/r['path']
    if sha(p) != r['sha256']: raise ValueError('Teacher array changed')
    journal.write(json.dumps(dict(event='OFFLINE_LABEL_NPZ_OPEN_AFTER_REPLAY',bag=record['bag'],
                                 fields=['stamp_ns', 'speed_mps', 'accepted'],sha256=r['sha256']))+'\n');journal.flush()
    with np.load(p, allow_pickle=False) as z:
        stamps, speed, accepted = z['stamp_ns'], z['speed_mps'], z['accepted']
    if stamps.dtype.kind != 'i' or speed.dtype.kind != 'f' or accepted.dtype.kind != 'b':
        raise ValueError('Teacher field dtype mismatch')
    if stamps.ndim != 1 or stamps.shape != speed.shape or stamps.shape != accepted.shape:
        raise ValueError('Teacher field shape mismatch')
    if len(stamps) != r['teacher_rows'] or int(accepted.sum()) != r['accepted_rows']:
        raise ValueError('Teacher row count mismatch')
    if np.any(accepted & (~np.isfinite(speed) | (speed < 0))): raise ValueError('Invalid accepted target')
    origin = record['sensor_start_ns']
    return IndexedTeacher(TeacherPoint((int(t)-origin)/1e9,float(v),True) for t,v in zip(stamps[accepted],speed[accepted]))


def replay_passive(events):
    c, rc = profile(); cn, rn = profile()
    probe = CausalFeatureProbe(c, readout=rc)
    native = GuardedReadoutObserver(cn, readout=rn)
    tp, tn = Timeline(probe, 20., 0.), Timeline(native, 20., 0.)
    rows=[]; features=[]; reason_codes=[]; counts=Counter(); statuses=Counter(); modes=Counter()
    max_hist=0; causal_errors=0; compared=0; state_fields=len(vars(native))
    for t, ch, v in events:
        tp.ingest(ch, Sample(float(t),float(v)));tn.ingest(ch,Sample(float(t),float(v)))
        for xp, xn in zip_longest(tp.advance(),tn.advance()):
            if xp is None or xn is None or xp != xn:
                raise AssertionError('Passive probe changed output or schedule')
            e, held = xp
            for key, value in vars(native).items():
                if getattr(probe, key) != value: raise AssertionError('Passive probe changed native state: '+key)
            compared += 1
            causal_errors += sum(s is not None and s.t > e.t+1e-9 for s in held)
            fr = probe.last_features
            reason_codes.append([REASONS.index(x.reason) for x in fr])
            for x in fr: counts[x.reason]+=1
            statuses[(e.front_status,e.rear_status)] += 1; modes[e.mode]+=1
            features.append([x.values if x.values is not None else (math.nan,)*8 for x in fr])
            rows.append([e.t,e.v,e.s, *(s.t if s is not None else math.nan for s in held[1:]),
                         *(s.value if s is not None else math.nan for s in held[1:])])
            for h in probe._h47_histories:
                max_hist=max(max_hist,len(h))
                if len(h)>16 or (h and e.t-h[0][0]>1.0): raise AssertionError('Unbounded runtime feature history')
    for key in ('resets','dropped','catchup_events','held','queues','next_tick','tick_index'):
        if getattr(tp,key) != getattr(tn,key): raise AssertionError('Timeline counters/state differ')
    a=np.asarray(rows,dtype=float).reshape((-1,7))
    if not np.all(np.isfinite(a[:,:3])) or (len(a)>1 and np.any(np.diff(a[:,0])<=0)):
        raise AssertionError('Nonfinite/nonmonotone output')
    return dict(outputs=a, features=np.asarray(features,dtype=float).reshape((-1,2,8)),
                feature_reason=np.asarray(reason_codes,dtype=np.uint8).reshape((-1,2))), dict(
        output_ticks=len(a), state_comparisons=compared, native_fields_per_tick=state_fields,
        native_state_and_estimate_exact=True, feature_reasons=dict(counts), modes=dict(modes),
        status_pairs={a+'|'+b:n for (a,b),n in statuses.items()}, max_feature_history=max_hist,
        causal_errors=causal_errors,resets=tp.resets,dropped=tp.dropped,catchups=tp.catchup_events)


def label_saved(arrays, teacher):
    outputs, fs, reasons=arrays['outputs'],arrays['features'],arrays['feature_reason']
    labels=np.full((len(outputs),2),-1,dtype=np.int8)
    reason=np.zeros(len(outputs),dtype=np.uint8)
    matched=np.full((len(outputs),2,2),np.nan,dtype=float)
    for k in np.flatnonzero(np.all(reasons==0,axis=1)):
        t,v,s,ft,rt,fv,rv=outputs[k]
        front,rear=Sample(ft,fv),Sample(rt,rv)
        tf,tr=teacher.nearest(ft),teacher.nearest(rt)
        for i,x in enumerate((tf,tr)):
            if x is not None:matched[k,i]=(x.t,x.speed_magnitude)
        if tf is None or tr is None:reason[k]=1;continue
        if min(abs(fv),abs(rv),tf.speed_magnitude,tr.speed_magnitude)<1.:
            reason[k]=2;continue
        result=proxy_pair_labels(front,rear,tf,tr,features_ready=True)
        if result is None:reason[k]=3;continue
        labels[k]=result
        reason[k]=4 if result==(0,0) else 5 if result==(1,0) else 6
    arrays.update(labels=labels,label_reason=reason,matched_teacher=matched)
    seen=set();clean=bad=0;bad_times=[]
    for k in np.flatnonzero(np.any(labels>=0,axis=1)):
        for ch in range(2):
            key=(ch,float(outputs[k,3+ch]))
            if key in seen:raise AssertionError('A sample was labelled more than once')
            seen.add(key)
            clean+=int(labels[k,ch]==0);bad+=int(labels[k,ch]==1)
            if labels[k,ch]==1:bad_times.append(float(outputs[k,0]))
    return dict(ready_pairs=int(np.sum(np.all(reasons==0,axis=1))),
                clean_updates=clean,fault_updates=bad,
                front_fault_updates=int(np.sum(labels[:,0]==1)),rear_fault_updates=int(np.sum(labels[:,1]==1)),
                label_reasons={LABEL_REASONS[i]:int(np.sum(reason==i)) for i in range(len(LABEL_REASONS))},
                episode_onsets_s=episode_onsets(bad_times),fault_times_s=bad_times)


def savez(path, arrays):
    # Deterministic NPZ, safe to compare hashes across independent repeats.
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name, value in sorted(arrays.items()):
            b=io.BytesIO();np.lib.format.write_array(b,np.asarray(value),allow_pickle=False)
            info=zipfile.ZipInfo(name+'.npy',(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16;z.writestr(info,b.getvalue())


def write_csv(path, rows):
    with Path(path).open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['empty']);w.writeheader();w.writerows(rows)


def aggregate(bags, reps):
    group_rows=[]
    by_group=defaultdict(list)
    for b in bags:
        if reps[b['bag']]==b['bag']:by_group[(b['fold'],b['group'])].append(b)
    for (fold,g), rows in sorted(by_group.items()):
        clean=sum(b['clean_updates'] for b in rows);bad=sum(b['fault_updates'] for b in rows)
        me=max((len(b['episode_onsets_s']) for b in rows),default=0)
        group_rows.append(dict(fold=fold,group=g,unique_wire_bags=len(rows),
            ready_pairs=sum(b['ready_pairs'] for b in rows),clean_updates=clean,fault_updates=bad,
            max_episodes_same_bag=me,qualified=qualifies_group(bad,clean,me)))
    return group_rows


def run(args):
    lock=json.loads(Path(args.lock).read_text());out=Path(args.output)
    if out.exists():raise FileExistsError('Never overwrite a coverage run')
    if lock.get('status')!='DEPENDENCIES_VERIFIED' or lock.get('baseline_sha')!=BASE or not lock.get('coverage_authorized'):
        raise PermissionError('Successful H47 dependency lock required')
    for name,h in lock['source_files'].items():
        if sha(ROOT/name)!=h:raise ValueError('Source changed since preflight: '+name)
    checked_json(Path(args.teacher_root)/'R5_HANDOFF.json',TEACHER)
    for r in lock['records']:safe_train_record(r)
    out.mkdir(parents=True);(out/'bags').mkdir();(out/'traces').mkdir()
    started=dict(hypothesis_id='R5-H47',stage='COVERAGE_ONLY',baseline_sha=BASE,
                 diagnostic_source_sha=args.source_sha,lock_sha256=sha(args.lock),optimizer_calls=0,
                 python=platform.python_version(),numpy=np.__version__,config=asdict(profile()[0]),readout=asdict(profile()[1]),
                 probe_module=str(HERE/'features.py'),native_module=str(ROOT/'src/reserve_odometry/reserve_odometry/guarded_readout.py'),
                 feature_names=FEATURE_NAMES,feature_reason_codes=REASONS,label_reason_codes=LABEL_REASONS,
                 teacher_usage='Only stamp_ns/speed_mps/accepted, AFTER vehicle replay; offline labels, not runtime features')
    save(out/'STARTED.json',started)
    bags=[];start=time.monotonic()
    with (out/'access.jsonl').open('x',encoding='utf-8') as journal:
        for r in sorted(lock['records'],key=lambda r:r['bag']):
            events=load_vehicle_events(r,args.data_root,journal)
            arrays,stats=replay_passive(events)
            teacher=load_teacher(r,args.teacher_root,journal)
            labels=label_saved(arrays,teacher)
            result=dict(bag=r['bag'],group=r['group'],fold=r['fold'],wire_sha256=r['wire_sha256'],
                        coverage_representative=lock['representatives'][r['bag']],
                        source_events=len(events),teacher_accepted=r['teacher']['accepted_rows'],**stats,**labels)
            trace=out/'traces'/(r['bag']+'.npz');savez(trace,arrays)
            result['trace_sha256']=sha(trace)
            save(out/'bags'/(r['bag']+'.json'),result);bags.append(result)
            print(json.dumps({k:result[k] for k in ('bag','fold','output_ticks','ready_pairs','clean_updates','fault_updates')}) ,flush=True)
    groups=aggregate(bags,lock['representatives'])
    fold_rows=[]
    for fold,need in [('fit',3),('check',2)]:
        gs=[g for g in groups if g['fold']==fold]
        bs=[b for b in bags if b['fold']==fold and lock['representatives'][b['bag']]==b['bag']]
        fold_rows.append(dict(fold=fold,source_groups=len(gs),unique_wire_bags=len(bs),
            ready_pairs=sum(b['ready_pairs'] for b in bs),clean_updates=sum(b['clean_updates'] for b in bs),
            fault_updates=sum(b['fault_updates'] for b in bs),fault_bearing_groups=sum(g['fault_updates']>0 for g in gs),
            qualified_groups=sum(g['qualified'] for g in gs),required_qualified_groups=need,
            passed=sum(g['qualified'] for g in gs)>=need))
    passed=all(x['passed'] for x in fold_rows)
    summary=dict(hypothesis_id='R5-H47',stage='FOUNDATION_PASSED' if passed else 'FOUNDATION_FAILED',
        scientific_verdict='NOT_EVALUATED' if passed else 'INCONCLUSIVE',foundation_passed=passed,
        diagnostic_source_sha=args.source_sha,baseline_sha=BASE,baseline_tree=TREE,
        plan_sha=lock['plan_sha'],lock_sha256=sha(args.lock),bags=len(bags),unique_wire_streams=len(set(lock['representatives'].values())),
        folds=fold_rows,raw_all_bag_clean_updates=sum(b['clean_updates'] for b in bags),
        raw_all_bag_fault_updates=sum(b['fault_updates'] for b in bags),
        exact_native_state_comparison_ticks=sum(b['state_comparisons'] for b in bags),
        native_fields_per_tick=sorted(set(b['native_fields_per_tick'] for b in bags)),
        native_state_and_estimate_exact=all(b['native_state_and_estimate_exact'] for b in bags),
        max_history_entries=max(b['max_feature_history'] for b in bags),
        causal_errors=sum(b['causal_errors'] for b in bags),
        optimizer_calls=0,candidate_implemented=False,candidate_sha=None,freeze_sha=None,
        odometry_accuracy_metrics=None,accuracy_contract_evaluated=False,ready_to_merge=False,
        validation_opened=False,test_opened=False,development_opened=False,
        elapsed_wall_seconds=time.monotonic()-start,
        next_step='One preregistered fit may start; this run does NOT fit' if passed else 'Do not fit; preserve insufficient natural faulty-example coverage without weakening the registered thresholds')
    write_csv(out/'per_group.csv',groups);write_csv(out/'per_fold.csv',fold_rows)
    columns=('bag','fold','group','coverage_representative','source_events','output_ticks','ready_pairs','teacher_accepted',
             'clean_updates','fault_updates','front_fault_updates','rear_fault_updates','max_feature_history','causal_errors','trace_sha256')
    write_csv(out/'per_bag.csv',[{k:b[k] for k in columns} for b in bags])
    save(out/'SUMMARY.json',summary)
    save(out/'RAW_MANIFEST.json',{str(p.relative_to(out)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(out.rglob('*')) if p.is_file()})
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='stage',required=True)
    a=sub.add_parser('prepare')
    for key in ('output','receipts','launch','source-zip','dataset-zip','teacher-root','atlas-root','data-root'):a.add_argument('--'+key,required=True)
    b=sub.add_parser('run')
    for key in ('lock','output','data-root','teacher-root','source-sha'):b.add_argument('--'+key,required=True)
    args=p.parse_args()
    try:(prepare if args.stage=='prepare' else run)(args)
    except (ValueError,PermissionError,FileExistsError) as e:p.exit(2,str(e)+'\n')

if __name__=='__main__':main()
