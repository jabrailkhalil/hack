"""Fixed v8/residual070 on the user-supplied checker bag; NEVER tunes or promotes.

The published ROS checker arithmetic is imported from checksum-verified AST
nodes. rclpy/DDS are NOT simulated or certified. Primary replay is the unchanged
native evaluator; receive-order two-stream synchronization and a 100 Hz timer
are offline sensitivities. Localization is evaluation-only, never a model input.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import sqlite3
import sys
from types import SimpleNamespace as NS

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BAG = '30618_88aea4d9'
DB_SHA = '48f846d134d0584b38f9ca06b7ba812a16aeeecc896594313e3fa9acd27e10c3'
CHECKER_SHA = '3f6e46923ad431d7ae4f811ff144cbca00c572a1631277dcaa3659cdf8e7a058'  # Filled from the uploaded bytes, not a remote reimplementation.
NAMES = ('main', 'disturbance_070')
CHANNELS = {'/vehicle/driver_position_cmd': 0, '/vehicle/front_bogie_velocity': 1,
            '/vehicle/rear_bogie_velocity': 2}
REFERENCE = '/localization/kinematic_state'


def sha(path: Path) -> str:
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


def frozen_sources():
    target = ROOT/'research/v8_targeted'
    pins = json.loads((target/'BASELINE_PINS.json').read_text())
    pins.update({'research/v8_targeted/'+p: h for p, h in
                 json.loads((target/'FREEZE.json').read_text())['source_sha256'].items()})
    for path, expected in pins.items():
        if sha(ROOT/path) != expected:
            raise ValueError('Frozen file changed: '+path)
    return pins


frozen_sources()
e = module('uploaded_checker_frozen_eval', ROOT/'research/v8_targeted/evaluate.py')
supp = module('uploaded_checker_frozen_supp', ROOT/'research/v8_targeted/supplemental.py')
from export_bags import CDR, decode
from reserve_odometry.core import Sample
from reserve_odometry.timeline import Timeline


def cdr_string(d: CDR) -> str:
    length = d.take('I', 4)
    if not 1 <= length <= 4096 or d.pos+length > len(d.raw) or d.raw[d.pos+length-1] != 0:
        raise ValueError('Invalid CDR string')
    text = d.raw[d.pos:d.pos+length-1].decode('utf-8')
    d.pos += length
    return text


def decode_odometry(raw: bytes) -> dict:
    d = CDR(raw)
    sec, ns = d.take('iI', 4)
    if ns >= 1_000_000_000: raise ValueError('Invalid nanoseconds')
    frame, child = cdr_string(d), cdr_string(d)
    xyz, quaternion = d.take('3d', 8), d.take('4d', 8)
    pose_covariance, twist, twist_covariance = d.take('36d', 8), d.take('6d', 8), d.take('36d', 8)
    if len(raw) != d.pos: raise ValueError('Unexpected Odometry payload size')
    return dict(stamp_ns=sec*1_000_000_000+ns, frame=frame, child=child, xyz=xyz,
                quaternion=quaternion, twist=twist, pose_covariance=pose_covariance,
                twist_covariance=twist_covariance)


@dataclass
class Data:
    origin_ns: int
    events: np.ndarray
    input_receipts: np.ndarray
    references: list
    gnss: dict
    inventory: dict


def load_data(checker_root: Path) -> Data:
    db = checker_root/'bags'/BAG/(BAG+'_0.db3')
    if sha(db) != DB_SHA: raise ValueError('Uploaded DB checksum mismatch')
    records = json.loads((ROOT/'research/split_v3.json').read_text())['records']
    if any(r['bag'] == BAG or r['sha256'] == DB_SHA for r in records):
        raise ValueError('New bag unexpectedly overlaps frozen split; review role first')
    # Two separate collections: only the three vehicle topics go to the estimator.
    raw_inputs, references = [], []
    gnss = {'master': [], 'rover': []}
    inventory = {}
    with sqlite3.connect(db.resolve().as_uri()+'?mode=ro', uri=True) as con:
        if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok': raise ValueError('SQLite integrity')
        for name, typ, count in con.execute('SELECT t.name,t.type,count(m.id) FROM topics t LEFT JOIN messages m ON m.topic_id=t.id GROUP BY t.id'):
            inventory[name] = dict(type=typ, count=count)
        if set(inventory) != set(CHANNELS)|{REFERENCE}|{f'/sensing/gnss/{r}/{s}' for r in gnss for s in ('vel','fix')}:
            raise ValueError('Unexpected topic inventory')
        query = ('SELECT m.id,m.timestamp,t.name,t.type,m.data FROM messages m JOIN topics t ON m.topic_id=t.id '
                 'ORDER BY m.timestamp,m.id')
        for mid, receipt, topic, typ, raw in con.execute(query):
            if topic in CHANNELS:
                stamp, values = decode(raw, typ)
                channel = CHANNELS[topic]
                value = float(values[0])/(15 if channel == 0 else 3.6)
                raw_inputs.append((receipt, mid, stamp, channel, value))
            elif topic == REFERENCE:
                if typ != 'nav_msgs/msg/Odometry': raise ValueError('Wrong reference type')
                value = decode_odometry(raw)
                if not all(math.isfinite(x) for x in (*value['xyz'], *value['twist'], *value['quaternion'])):
                    raise ValueError('Nonfinite reference; do not silently clean it')
                references.append(dict(value, receipt_ns=receipt, message_id=mid))
            elif topic.endswith('/vel'):
                stamp, v = decode(raw, typ)
                gnss[topic.split('/')[3]].append((stamp, math.hypot(v[0], v[1])))
            # GNSS fixes are inventoried only. No GNSS initialization/correction is run.
    if not raw_inputs or not references: raise ValueError('Empty inputs or reference')
    origin = min(row[2] for row in raw_inputs)
    events = np.array([((r[2]-origin)/1e9,r[3],r[4]) for r in raw_inputs], float)
    receipts = np.array([r[0] for r in raw_inputs], np.int64)
    for topic, channel in CHANNELS.items():
        rows = [r for r in raw_inputs if r[3] == channel]
        stamps = np.array([r[2] for r in rows], np.int64)
        latency = np.array([(r[0]-r[2])/1e9 for r in rows])
        inventory[topic].update(backwards=int(np.sum(np.diff(stamps)<0)), duplicates=int(np.sum(np.diff(stamps)==0)),
                                maximum_stamp_gap_s=float(np.max(np.diff(stamps))/1e9),
                                receipt_minus_stamp_s=dict(zip(['min','median','p99','max'],map(float,np.quantile(latency,[0,.5,.99,1])))))
    for rec in gnss:
        gnss[rec] = [((t-origin)/1e9,v) for t,v in gnss[rec]]
    return Data(origin, events, receipts, references, gnss, inventory)


def fixed_models():
    from dataclasses import asdict
    result = e.c.models(NAMES)
    a,b = (asdict(result[n][1]) for n in NAMES)
    if [k for k in a if a[k] != b[k]] != ['disturbance_limit_mps2'] or b['disturbance_limit_mps2'] != .7000000000000001:
        raise ValueError('Selected numerical profile changed')
    return result


def nearest(reference_ns, prediction_ns, tolerance_ns=50_000_000):
    reference_ns = np.asarray(reference_ns, np.int64)
    prediction_ns = np.asarray(prediction_ns, np.int64)
    if not len(reference_ns): return np.zeros(len(prediction_ns), int), np.zeros(len(prediction_ns), bool)
    if np.any(np.diff(reference_ns) <= 0): raise ValueError('Reference stamps must be strictly increasing')
    j = np.searchsorted(reference_ns, prediction_ns)
    lo, hi = np.clip(j-1,0,len(reference_ns)-1), np.clip(j,0,len(reference_ns)-1)
    # Same later-on-tie rule as frozen ex.match. No float epoch conversion.
    idx = np.where(abs(reference_ns[lo]-prediction_ns)<abs(reference_ns[hi]-prediction_ns),lo,hi)
    return idx, abs(reference_ns[idx]-prediction_ns) <= tolerance_ns


def load_checker(checker_root: Path):
    path = checker_root/'src/checker_ros/hackathon_solution_checker/metrics.py'
    if sha(path) != CHECKER_SHA: raise ValueError('Checker checksum mismatch')
    original = ast.parse(path.read_text())
    imports = ast.parse('from __future__ import annotations\nfrom dataclasses import dataclass\nimport math\nfrom typing import Any, Iterable, Sequence\n').body
    names = {'ErrorAccumulator','get_numeric_field','position_errors','MetricsNode'}
    selected = [n for n in original.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names]
    if len(selected) != len(names): raise ValueError('Checker AST surface changed')
    namespace = {'__name__':'_uploaded_checker_arithmetic', 'Node':object}
    obj = NS(__dict__=namespace)
    # dataclasses looks up the module namespace when postponed annotations are used.
    from types import ModuleType
    mod = ModuleType(namespace['__name__']);sys.modules[mod.__name__]=mod;mod.__dict__.update(namespace)
    exec(compile(ast.Module(body=imports+selected,type_ignores=[]),str(path),'exec'),mod.__dict__)
    return mod


def message(stamp_ns, velocity, xyz, frame, child='base_link'):
    sec, ns = divmod(int(stamp_ns),1_000_000_000)
    return NS(header=NS(stamp=NS(sec=sec,nanosec=ns),frame_id=frame), child_frame_id=child,
              velocity=float(velocity), twist=NS(twist=NS(linear=NS(x=float(velocity)))),
              pose=NS(pose=NS(position=NS(x=float(xyz[0]),y=float(xyz[1]),z=float(xyz[2])))))


def exact_arithmetic(checker, reference, predictions, pairs):
    node = checker.MetricsNode.__new__(checker.MetricsNode)
    node.velocity_metric = checker.ErrorAccumulator()
    node.position_metrics = {k:checker.ErrorAccumulator() for k in ('x','y','z','distance')}
    node.reference_velocity_field='twist.twist.linear.x';node.result_velocity_field='velocity';node._field_error_reported=False
    for ri,pi in pairs:
        ref=reference[int(ri)];pred=predictions[int(pi)]
        a=message(ref['stamp_ns'],ref['twist'][0],ref['xyz'],ref['frame'],ref['child'])
        b=message(pred[0],pred[1],(pred[2],0.,0.),'odom_path_1d')
        # Unmodified uploaded callbacks. There is no transform or frame check in them.
        node._on_velocity_pair(a,b);node._on_position_pair(a,b)
    def summary(m): return dict(n=m.count,rmse=m.rmse if m.count else None,maximum_error=m.maximum_error if m.count else None)
    return dict(velocity=summary(node.velocity_metric),raw_position={k:summary(m) for k,m in node.position_metrics.items()},
                reference_frames=sorted({r['frame'] for r in reference}),reference_child_frames=sorted({r['child'] for r in reference}),
                result_frame='odom_path_1d',position_frames_compatible=False,
                position_warning='Direct coordinate subtraction across different frames; not meaningful localization accuracy. Checker itself does not transform/reject frames.')


class PairSync:
    """Two timestamped streams: Humble ATS two-queue semantics, offline only.

    Queue=100 per stream; evict smallest stamp; pick nearest to the new message;
    final acceptance is strictly <50ms. Matched messages are consumed once.
    No DDS jitter, QoS drops, callbacks on other executor threads or ROS clocks.
    """
    def __init__(self, queue_size=100, tolerance_ns=50_000_000):
        if queue_size<1 or tolerance_ns<0:raise ValueError('Invalid sync configuration')
        self.q=[{},{}];self.queue_size=queue_size;self.tolerance_ns=tolerance_ns;self.pairs=[];self.evicted=[0,0]
    def add(self, stream, stamp, index):
        mine,other=self.q[stream],self.q[1-stream]
        mine[int(stamp)]=int(index)
        while len(mine)>self.queue_size: del mine[min(mine)];self.evicted[stream]+=1
        valid=[s for s in other if abs(s-stamp)<=self.tolerance_ns]
        if not valid:return
        match=min(valid,key=lambda s:abs(s-stamp))
        if abs(match-stamp)<self.tolerance_ns:
            pair=(other.pop(match),mine.pop(int(stamp)))
            self.pairs.append(pair if stream==1 else pair[::-1])


def scheduled_replay(data: Data, model, timer_phase_ns=None):
    factory,config=model;tl=Timeline(factory(config),rate_hz=20.,delay_s=0.)
    output,publications=[],[];mode_counts=Counter();causal_errors=0
    next_timer=int(data.input_receipts[0])+(timer_phase_ns or 0)
    def advance(receipt):
        nonlocal causal_errors
        for value,held in tl.advance():
            if value.mode=='WAITING_FOR_INITIALIZATION':continue
            causal_errors+=sum(s is not None and s.t>value.t+1e-9 for s in held)
            mode_counts[value.mode]+=1
            wheels=[s.value if s is not None and 0<=value.t-s.t<=config.max_age_s else np.nan for s in held[1:]]
            output.append([value.t,value.v,value.s,wheels[0],sum(wheels)/2,value.mode=='STOPPED'])
            publications.append(receipt)
    for receipt,(t,ch,value) in zip(data.input_receipts,data.events):
        receipt=int(receipt)
        if timer_phase_ns is not None:
            while next_timer<=receipt:advance(next_timer);next_timer+=10_000_000
        tl.ingest(int(ch),Sample(float(t),float(value)))
        if timer_phase_ns is None:advance(receipt)
    if timer_phase_ns is not None:
        while next_timer<=int(data.input_receipts[-1])+1_000_000_000:advance(next_timer);next_timer+=10_000_000
    return np.array(output,float).reshape(-1,6),np.array(publications,np.int64),dict(resets=tl.resets,dropped=tl.dropped,catchups=tl.catchup_events,causal_errors=causal_errors,mode_counts=dict(mode_counts))


def stamp_predictions(data, arrays):
    # Keep int64 epoch nanoseconds separate: float arrays must never hold epoch times.
    t=data.origin_ns+np.rint(arrays[:,0]*1e9).astype(np.int64)
    return [(int(ns),float(row[1]),float(row[2])) for ns,row in zip(t,arrays)]


def sync_pairs(references, predictions, publications):
    sync=PairSync()
    arrivals=[(r['receipt_ns'],0,i,r['stamp_ns']) for i,r in enumerate(references)]
    arrivals += [(int(t),1,i,int(p[0])) for i,(p,t) in enumerate(zip(predictions,publications))]
    # Explicit deterministic tie order: reference before result, then stream index.
    for _,kind,i,stamp in sorted(arrivals):sync.add(kind,stamp,i)
    return np.array(sync.pairs,int).reshape(-1,2),dict(evicted=sync.evicted,pending=[len(q) for q in sync.q])


def integrity(clean, faulted, fault):
    if clean.shape != faulted.shape or not np.array_equal(clean[:,0],faulted[:,0]):raise AssertionError('Schedule differs')
    before=clean[:,0]<fault['start']
    if not np.array_equal(clean[before,:3],faulted[before,:3]):raise AssertionError('Prefault changed')
    delta_v=faulted[:,1]-clean[:,1];delta_s=faulted[:,2]-clean[:,2]
    v_integral=np.r_[0.,np.cumsum(.5*(delta_v[:-1]+delta_v[1:])*np.diff(clean[:,0]))]
    error=float(np.max(abs(delta_s-delta_s[0]-v_integral)))
    if not math.isfinite(error) or error>1e-7:raise AssertionError('Distance integral')
    return dict(max_integral_error_m=error,terminal_fault_minus_clean_s_m=float(delta_s[-1]))


def relabel_distance(x):
    """Reference label only; never alter scorer outputs, formulas, masks or values."""
    if isinstance(x,dict):
        if 'definition' in x and 'GNSS speed' in str(x['definition']):
            x['definition']='s versus integral of matched /localization/kinematic_state linear.x; NOT XYZ'
        for v in x.values():relabel_distance(v)
    elif isinstance(x,list):
        for v in x:relabel_distance(v)


def run(checker_root: Path, output: Path):
    output.mkdir(parents=True,exist_ok=False)
    pins=frozen_sources();models=fixed_models();checker=load_checker(checker_root)
    save(output/'STARTED.json',dict(utc=datetime.now(timezone.utc).isoformat(),runner_sha256=sha(Path(__file__)),pins=pins,
         models=e.c.manifest(NAMES),bag=BAG,db_sha256=DB_SHA,checker_sha256=CHECKER_SHA,
         role='additional_uploaded_checker_bag',fitting_calls=0,parameters_changed=False,
         protocol_note='Runner finalized after preliminary schema inspection/replay; no candidate tuning. Not pre-registered independent validation.',
         python=platform.python_version(),numpy=np.__version__))
    data=load_data(checker_root)
    ordered=sorted(data.references,key=lambda r:r['stamp_ns'])
    reference_ns=np.array([r['stamp_ns'] for r in ordered],np.int64)
    if np.any(np.diff(reference_ns)<=0):raise ValueError('Reference duplicates/reversals need explicit treatment')
    refs={'kinematic':[((r['stamp_ns']-data.origin_ns)/1e9,r['twist'][0]) for r in ordered]}
    result=dict(role='additional_uploaded_checker_bag',bag=BAG,models=NAMES,inventory=data.inventory,
                reference_count=len(ordered),recorded_duration_s=(max(r['receipt_ns'] for r in ordered)-int(data.input_receipts[0]))/1e9,
                first_reference={k:ordered[0][k] for k in ('frame','child','xyz','quaternion')},native={},timer={},
                original_faults=[],low=[],common=[],slow=[],integrity=[],ready_to_merge=False)
    native,info=e.predictions(data.events,models)
    result['native_frozen_metrics']=e.score_arrays(native,info,refs)
    result['sparse_GNSS_diagnostic']=e.score_arrays(native,info,data.gnss)
    for n in NAMES:
        a=native[n];scheduled,pub,diag=scheduled_replay(data,models[n])
        if not np.array_equal(a,scheduled,equal_nan=True) or diag!=info[n]:raise AssertionError('Native replay reproduction differs')
        predictions=stamp_predictions(data,a);j,ok=nearest(reference_ns,[p[0] for p in predictions])
        pairs=np.column_stack((j[ok],np.flatnonzero(ok)))
        primary=exact_arithmetic(checker,ordered,predictions,pairs)
        baseline_rmse=result['native_frozen_metrics']['receivers']['kinematic'][n]['rmse']
        if not math.isclose(primary['velocity']['rmse'],baseline_rmse,rel_tol=1e-12):raise AssertionError('Checker/numpy formula parity')
        primary['coverage']=len(pairs)/len(a);primary['runtime']=diag
        primary['max_header_gap_ms']=float(np.max(abs(reference_ns[j[ok]]-np.array([p[0] for p in predictions],np.int64)[ok]))/1e6)
        ats,diagnostics=sync_pairs(data.references,predictions,pub)
        primary['arrival_order_sync']=dict(**exact_arithmetic(checker,data.references,predictions,ats),diagnostics=diagnostics,coverage=len(ats)/len(a))
        result['native'][n]=primary
        np.savez_compressed(output/(n+'-native.npz'),predictions=a,publish_receipt_ns=pub,nearest_pairs=pairs,sync_pairs=ats)
    for phase in (0,5_000_000):
        label=str(phase)+'ns';result['timer'][label]={}
        for n in NAMES:
            a,pub,diag=scheduled_replay(data,models[n],phase);pred=stamp_predictions(data,a)
            pairs,sync_diag=sync_pairs(data.references,pred,pub)
            score=exact_arithmetic(checker,data.references,pred,pairs)
            score.update(coverage=len(pairs)/len(a),outputs=len(a),runtime=diag,synchronizer=sync_diag)
            result['timer'][label][n]=score
            np.savez_compressed(output/(n+'-timer-'+label+'.npz'),predictions=a,publish_receipt_ns=pub,sync_pairs=pairs)
    for i,(fault,window) in enumerate(e.g.fault_windows(data.events)):
        row=dict(fault=fault,cropped=e.g.compare(window,refs,models,fault))
        changed,rt=e.predictions(data.events,models,fault)
        row['full']=e.score_arrays(changed,rt,refs)
        row['integrity']={n:integrity(native[n],changed[n],fault) for n in NAMES}
        result['original_faults'].append(row)
        np.savez_compressed(output/('fault-'+str(i)+'.npz'),**changed)
    for f,w in supp.low_windows(data.events):result['low'].append(dict(fault=f,**e.g.compare(w,refs,models,f)))
    for k,generator in [('common',supp.common_windows),('slow',supp.slow_windows)]:
        for f,w in generator(data.events):result[k].append(dict(fault=f,**supp.compare_injected(w,refs,models,f)))
    a,b=(result['native'][n]['velocity']['rmse'] for n in NAMES)
    result['native_speed_rmse_change_percent']=100*(b/a-1)
    result['native_selected_max_velocity_delta_mps']=float(np.max(abs(native[NAMES[1]][:,1]-native[NAMES[0]][:,1])))
    result['caveats']=['One new bag, NOT the frozen nineteen-bag validation.',
        'Closest-time primary arithmetic and receive-order synchronizer sensitivity are NOT a live DDS/ROS checker run.',
        'No map supplied: raw XYZ score compares odom_path_1d with map; never treat it as valid localization accuracy.',
        'The uploaded relay_result.py copies reference pose AND reference velocity; it is not an estimator and was NOT run.',
        'Sparse GNSS scores are supplemental only; the supplied checker uses kinematic_state linear.x.',
        'Speed integral distance surrogate is NOT map position; no alignment fitted to the reference.',
        'No tuning, no runtime use of kinematic_state or GNSS, no final-test split payloads decoded.']
    relabel_distance({k:v for k,v in result.items() if k != 'sparse_GNSS_diagnostic'})
    frozen_sources()
    if sha(checker_root/'bags'/BAG/(BAG+'_0.db3'))!=DB_SHA:raise AssertionError('DB changed')
    save(output/'RESULT.json',result)
    save(output/'MANIFEST.json',{p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file()})
    print(json.dumps({k:result[k] for k in ('bag','native_speed_rmse_change_percent','native','timer')},indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checker-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(args.checker_root,args.output)
