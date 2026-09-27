"""Audit GNSS availability BEFORE the frozen Localizer, without reference IO.

Uses exact previously published raw-distance arrays: this is a new position-layer
availability replay, NOT a new speed benchmark, a ROS run or the hidden test.
All schedules are engineering stress scenarios, not organizer-promised rates.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import struct
import zipfile

import numpy as np
from pathgraph import Fix, Grid, Localizer, Pathgraph, Settings

PARENT = '2037ea16fb7a7b2777418ccc8924bdc688e1159d'
DB_SHA = '48f846d134d0584b38f9ca06b7ba812a16aeeecc896594313e3fa9acd27e10c3'
SOURCE_SHA = 'f1d2943a792757b6aae8632324152c6dce6242a6df928324b97b6b27ec68bbf4'
GRID_SHA = '84d597da6335507d9df054231adab8211681cf90c82b6e491d666d3e772fdca5'
TOPIC = '/sensing/gnss/rover/fix'
MAPS = {
    'maps/щукинская - таллинская (1).json': '036e2d746b87daa6f060485c93b2b8ef942a15f83d357ac252313f84b3ab50c9',
    'maps/таллинская - щукинская.json': '7a402fcd426a607ad2f6cf2fca7dbf38cf2e9a171cd5034c61eb3d71bc0e53ba',
}
CACHES = {
    'main': '1e76bf16d69aff37465f452af31484fe8149ff2a6ce99ed7e0d8d5512fcc02dd',
    'disturbance_070': 'bd091d8286e85a439e85c7565a90c9d323b87352ccb927e86a55e01942f4a2fb',
}
SCENARIOS = {
    'recorded': {},
    'no_gnss_resilience_only': {'warmup_s': 0},
    'initial_1s_only': {'warmup_s': 1},
    'initial_3s_only': {'warmup_s': 3},
    'initial_5s_only': {'warmup_s': 5},
    'initial_10s_only': {'warmup_s': 10},
    'initial_5s_then_one_per_30s': {'warmup_s': 5, 'period_s': 30},
    'initial_5s_then_one_per_60s': {'warmup_s': 5, 'period_s': 60},
    'initial_5s_then_2s_bursts_per_60s': {'warmup_s': 5, 'period_s': 60, 'burst_s': 2},
}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        h = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def decode_fix(raw: bytes, receipt: int) -> Fix:
    """NavSatFix CDR1 only. No localization message is deserialized."""
    if raw[:4] not in (b'\x00\x01\x00\x00', b'\x00\x00\x00\x00'):
        raise ValueError('Expected CDR1')
    endian = '<' if raw[1] == 1 else '>'
    offset = 4

    def take(fmt, alignment):
        nonlocal offset
        offset += -(offset-4) % alignment
        result = struct.unpack_from(endian+fmt, raw, offset)
        offset += struct.calcsize(endian+fmt)
        return result[0] if len(result) == 1 else result

    sec, ns = take('iI', 4)
    size = take('I', 4)
    if ns >= 10**9 or not 1 <= size <= 4096 or offset+size > len(raw) or raw[offset+size-1] != 0:
        raise ValueError('Invalid stamp/string')
    frame = raw[offset:offset+size-1].decode('utf-8'); offset += size
    status = take('b', 1); take('H', 2)
    lat, lon, _alt = take('3d', 8)
    take('9d', 8); take('B', 1)
    if len(raw)-offset not in range(8) or any(raw[offset:]):
        raise ValueError('Invalid CDR trailing bytes')
    return Fix(int(sec*10**9+ns), int(receipt), 'rover', lat, lon, status, frame)


def load_fixes(db: Path):
    if digest(db) != DB_SHA:
        raise ValueError('DB checksum differs')
    with sqlite3.connect(db.resolve().as_uri()+'?mode=ro', uri=True) as con:
        # Only permitted input topics establish the clock origin, never reference.
        allowed = (TOPIC, '/vehicle/driver_position_cmd', '/vehicle/front_bogie_velocity', '/vehicle/rear_bogie_velocity')
        start = con.execute('SELECT min(m.timestamp) FROM messages m JOIN topics t ON m.topic_id=t.id '
                            'WHERE t.name IN (?,?,?,?)', allowed).fetchone()[0]
        query = ('SELECT m.timestamp,m.data FROM messages m JOIN topics t ON m.topic_id=t.id '
                 'WHERE t.name=? AND t.type=? ORDER BY m.timestamp,m.id')
        fixes = [decode_fix(raw, receipt) for receipt, raw in con.execute(query, (TOPIC, 'sensor_msgs/msg/NavSatFix'))]
    if start is None or not fixes:
        raise ValueError('No GNSS/permitted input origin')
    return int(start), fixes


def select(fixes, origin_ns, warmup_s=None, period_s=None, burst_s=None):
    """Causal receipt-clock masking; do not pick fixes by quality or residual."""
    if warmup_s is not None and (warmup_s < 0 or not np.isfinite(warmup_s)):
        raise ValueError('Invalid initial duration')
    if period_s is not None and (warmup_s is None or period_s <= 0 or not np.isfinite(period_s)):
        raise ValueError('Invalid period')
    if burst_s is not None and (period_s is None or not 0 < burst_s <= period_s):
        raise ValueError('Invalid burst')
    initial_end = None if warmup_s is None else origin_ns+round(warmup_s*10**9)
    period = None if period_s is None else round(period_s*10**9)
    burst = None if burst_s is None else round(burst_s*10**9)
    last_receipt, next_slot = None, initial_end
    for fix in fixes:
        now = fix.receipt_ns
        if last_receipt is not None and now < last_receipt:
            raise ValueError('Input receipt order reversed')
        last_receipt = now
        if now < origin_ns:
            raise ValueError('Origin after input')
        if initial_end is None or now < initial_end:
            yield fix
        elif period is not None:
            if burst is not None:
                if (now-initial_end) % period < burst:
                    yield fix
            elif now >= next_slot:
                next_slot = now+period
                yield fix  # Invalid fixes still consume their scheduled slot.


def replay(routes, grid, cache, fixes):
    loc = Localizer(routes, grid, Settings(mode='sparse'))
    delivered, pending, decisions = 0, [], []
    prediction = np.full(cache['predictions'].shape, np.nan)
    prediction[:, 0] = cache['predictions'][:, 0]
    prediction[:, 5] = -1
    for i, (stamp, receipt, raw) in enumerate(zip(cache['source_ns'], cache['receipt_ns'], cache['raw_distance'])):
        while delivered < len(fixes) and fixes[delivered].receipt_ns <= receipt:
            pending.append(fixes[delivered]); delivered += 1
        due = [f for f in pending if f.stamp_ns <= stamp]
        pending = [f for f in pending if f.stamp_ns > stamp]
        if len(pending) > 128:
            raise ValueError('Future GNSS budget exceeded')
        point = loc.advance(int(stamp), float(raw), int(receipt), due)
        if point['xyz'] is not None:
            prediction[i, 1:4] = point['xyz']
        if point['s'] is not None:
            prediction[i, 4] = point['s']
        if point['route_index'] is not None:
            prediction[i, 5] = point['route_index']
        decisions.extend(d for d in loc.decisions if d['reason'] in ('initialized', 'corrected'))
    valid = np.all(np.isfinite(prediction[:, 1:4]), axis=1)
    return prediction, {
        'outputs': len(prediction), 'available_positions': int(valid.sum()), 'coverage': float(valid.mean()),
        'selected_rover_fixes': len(fixes), 'received_by_last_output': delivered,
        'fixes_processed': sum(loc.counts.values()), 'counts': dict(loc.counts),
        'decisions': decisions, 'accuracy_rmse': None,
        'accuracy_note': 'Availability audit only; no reference messages read.',
    }


def checked_bytes(bundle, name, expected):
    raw = bundle.read(name)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Published input checksum changed: '+name)
    return raw


def run(bundle_path: Path, db: Path, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).resolve().parent
    if digest(here/'pathgraph.py') != SOURCE_SHA or digest(here/'grid_hypothesis.json') != GRID_SHA:
        raise ValueError('Frozen map layer changed')
    plan_path = here/'AVAILABILITY_PLAN.md'
    save(output/'STARTED.json', {
        'utc': datetime.now(timezone.utc).isoformat(), 'parent_commit': PARENT,
        'plan_sha256': digest(plan_path), 'audit_source_sha256': digest(Path(__file__)),
        'pathgraph_source_sha256': SOURCE_SHA, 'scenarios': SCENARIOS,
        'speed_source': 'Pinned original raw-distance/velocity caches; speed NOT rerun.',
        'reference_topics_read': False, 'fitting_calls': 0, 'ROS_executed': False,
    })
    try:
        with zipfile.ZipFile(bundle_path) as bundle:
            routes = [Pathgraph(json.loads(checked_bytes(bundle, name, h)), name=name) for name, h in MAPS.items()]
            caches = {}
            for model, h in CACHES.items():
                data = checked_bytes(bundle, 'evidence/final/'+model+'-sparse.npz', h)
                with np.load(io.BytesIO(data), allow_pickle=False) as arrays:
                    caches[model] = {k: arrays[k].copy() for k in arrays.files}
                cache = caches[model]
                if cache['predictions'].shape != (26187, 6) or np.any(np.diff(cache['source_ns']) <= 0):
                    raise ValueError('Original output schedule mismatch')
                for value in cache.values():
                    value.flags.writeable = False
        origin, fixes = load_fixes(db)
        grid = Grid(**json.loads((here/'grid_hypothesis.json').read_text()))
        result = {
            'status': 'AUDITED_NOT_RELEASE_ADMISSION', 'parent_commit': PARENT,
            'receipt_origin_ns': origin, 'rover_fixes_in_bag': len(fixes),
            'GNSS_guaranteed_initial_duration_s': None, 'engineering_scenarios': SCENARIOS,
            'grid': asdict(grid), 'models': {}, 'baseline_reproduction_exact': True,
            'model_changed': False, 'reference_topics_read': False,
            'main_changed': False, 'ready_to_merge': False,
        }
        for model, cache in caches.items():
            result['models'][model] = {}
            for name, parameters in SCENARIOS.items():
                selected = list(select(fixes, origin, **parameters))
                prediction, row = replay(routes, grid, cache, selected)
                if name == 'recorded' and not np.array_equal(prediction, cache['predictions'], equal_nan=True):
                    raise AssertionError('Recorded-input baseline no longer matches the published arrays')
                result['models'][model][name] = row
                np.savez_compressed(output/(model+'-'+name+'.npz'), predictions=prediction,
                                    selected_stamp_ns=np.array([f.stamp_ns for f in selected], np.int64),
                                    selected_receipt_ns=np.array([f.receipt_ns for f in selected], np.int64))
                print(model, name, row['selected_rover_fixes'], row['available_positions'], flush=True)
        if digest(db) != DB_SHA or digest(here/'pathgraph.py') != SOURCE_SHA:
            raise ValueError('Inputs changed during replay')
        save(output/'RESULT.json', result)
        save(output/'MANIFEST.json', {p.name: digest(p) for p in output.iterdir() if p.is_file()})
        return result
    except Exception as exc:
        save(output/'FAILURE.json', {'status': 'INCOMPLETE_NOT_PASS', 'error': repr(exc)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.bundle, args.db, args.output)
