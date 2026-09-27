"""Development-only integration of the pinned candidate and route-localization lab."""
from bisect import bisect_left
from threading import Lock
from dataclasses import asdict, replace
from pathlib import Path
import csv
import io
import hashlib
import json
import math
import time
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from ..research.models import MODEL_ID
from ..research.route import Route, to_enu, finite
from ..research.localization import Fix, Localizer, Policy

ROOT = Path(__file__).parents[1]
MAX_POINTS = 180000


def contract():
    return json.loads((ROOT/'research/contract.json').read_text(encoding='utf-8'))


def allowed(bag):
    row = next((r for r in contract()['development'] if r['bag'] == bag), None)
    if row is None:
        raise ValueError('Research IO permits only the pinned 17 development bags, not train/validation/test')
    return row


def inside(root, relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError('Artifact path must be a nonempty string')
    root = Path(root).resolve()
    result = (root/relative).resolve()
    if result == root or not result.is_relative_to(root):
        raise ValueError('Unsafe artifact path')
    return result


def number(value):
    if value is None or value == '':
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def load_prediction(settings, run_id, bag):
    pin = allowed(bag)  # authorization before ANY run or bag payload IO
    folder = inside(settings.runs, run_id)
    provenance = json.loads((folder/'provenance.json').read_text(encoding='utf-8'))
    matches = [r for r in provenance['bags'] if r['id'] == bag]
    record = matches[0] if len(matches) == 1 else None
    if record is None or record['sha256'] != pin['sha256']:
        raise ValueError('Saved run has a different development bag hash')
    config = json.loads((folder/'config.json').read_text(encoding='utf-8'))
    if bag not in config.get('bags', []):
        raise ValueError('Prediction bag missing from saved run membership')
    path = inside(folder/'bags', bag+'/predictions.csv')
    with path.open('rb') as stream:
        content = stream.read(128*1024*1024+1)
    if len(content) > 128*1024*1024:
        raise ValueError('Prediction CSV exceeds 128 MiB')
    rows = []
    with io.StringIO(content.decode('utf-8'), newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'time_ns', 'velocity_mps', 'distance_m', 'reference_mps', 'matched'}
        if not required <= set(reader.fieldnames or []):
            raise ValueError('Missing prediction CSV columns')
        for raw in reader:
            if len(rows) >= MAX_POINTS:
                raise ValueError('Research UI supports at most 180000 ticks per bag')
            stamp = int(raw['time_ns'])
            if rows and stamp <= rows[-1]['time_ns']:
                raise ValueError('Non-monotonic predictions; split/reset episodes explicitly')
            rows.append(dict(time_ns=stamp, distance=number(raw.get('distance_m')),
                velocity=number(raw.get('velocity_mps')), reference=number(raw.get('reference_mps')),
                matched=raw.get('matched', '').lower() == 'true'))
    return rows, config, pin, hashlib.sha256(content).hexdigest()


def compare_predictions(a, b):
    if len(a) != len(b) or any(x['time_ns'] != y['time_ns'] for x, y in zip(a, b)):
        raise ValueError('Different publication schedules; not a paired comparison')
    if any(x['reference'] != y['reference'] or x['matched'] != y['matched'] for x, y in zip(a, b)):
        raise ValueError('Different reference or coverage masks; do not silently intersect them')
    valid = lambda r: r['matched'] and r['velocity'] is not None and r['reference'] is not None
    if any(valid(x) != valid(y) for x, y in zip(a, b)):
        raise ValueError('Different prediction availability at paired ticks')
    def metric(rows):
        errors = [r['velocity']-r['reference'] for r in rows
                  if r['matched'] and r['velocity'] is not None and r['reference'] is not None]
        return dict(count=len(errors), sse=math.fsum(e*e for e in errors),
                    rmse_mps=math.sqrt(math.fsum(e*e for e in errors)/len(errors)) if errors else None)
    x, y = metric(a), metric(b)
    if x['count'] != y['count']:
        raise ValueError('Different prediction availability')
    return {'baseline': x, 'candidate': y}


def summarize_pairs(rows):
    output = {}
    for model in ('baseline', 'candidate'):
        valid = [r for r in rows if r[model]['count']]
        groups = {}
        for r in valid:
            groups.setdefault(r['group'], []).append(r[model]['rmse_mps'])
        n = sum(r[model]['count'] for r in valid)
        output[model] = dict(samples=n, reference_bags=len(valid), reference_groups=len(groups),
            group_macro_rmse_mps=math.fsum(math.fsum(v)/len(v) for v in groups.values())/len(groups) if groups else None,
            pooled_rmse_mps=math.sqrt(math.fsum(r[model]['sse'] for r in valid)/n) if n else None)
    return output


def scope_comparison(settings, baseline, candidate, bags, vehicle):
    if not isinstance(bags, list) or not all(isinstance(b, str) for b in bags):
        raise ValueError('bags must be a list of strings')
    if vehicle not in ('30618', '30639', 'all') or len(bags) > 17 or len(set(bags)) != len(bags):
        raise ValueError('Invalid vehicle scope or duplicate bag selection')
    rows, sources, excluded = [], {}, []
    seen_hashes = set()
    for bag in bags:
        pin = allowed(bag)
        if vehicle != 'all' and bag.split('_')[0] != vehicle:
            excluded.append(bag)
            continue
        if pin['sha256'] in seen_hashes:
            raise ValueError('Duplicate database content must not receive a second comparison weight')
        seen_hashes.add(pin['sha256'])
        a, ca, _, ha = load_prediction(settings, baseline, bag)
        b, cb, _, hb = load_prediction(settings, candidate, bag)
        for key in ('faults', 'quality', 'period_ms', 'tolerance_ms', 'seed'):
            if ca.get(key) != cb.get(key):
                raise ValueError('Run settings differ: '+key)
        rows.append(dict(bag=bag, group=pin['group'], **compare_predictions(a, b)))
        sources[bag] = {'baseline_csv_sha256': ha, 'candidate_csv_sha256': hb}
    if not rows:
        raise ValueError('No paired bags in the requested development scope')
    return dict(scope=vehicle, role='reused_development', rows=rows, summary=summarize_pairs(rows),
                excluded_by_vehicle=excluded, sources=sources, official_score=False,
                note='Lab receipt-clock speed proxy; not the historical native v8 benchmark or XYZ score')


def selected_fixes(events, receiver, period_s, origin_ns, route, initial_window_s=0.):
    """Deterministic arrival-clock thinning, BEFORE model residual/quality checks.

    One first received message per time slot. A rejected message is NOT replaced
    by a more convenient fix from the same slot. The other antenna is not a
    second independent correction or a hindsight fallback.
    """
    last_slot = None
    last_receipt = None
    period_ns = round(period_s*1e9)
    for event in events:
        if last_receipt is not None and event.received_ns < last_receipt:
            raise ValueError('Events must remain in receipt order')
        last_receipt = event.received_ns
        if event.topic != '/sensing/gnss/'+receiver+'/fix':
            continue
        slot = (event.received_ns-origin_ns)//period_ns
        initial_phase = 0 <= event.received_ns-origin_ns <= round(initial_window_s*1e9)
        if slot == last_slot and not initial_phase:
            continue
        last_slot = slot
        d = event.data
        try:
            xyz = to_enu(d['latitude'], d['longitude'], d['altitude'], route.origin)
            status = d['status']
            if not finite(status) or status not in (0, 1, 2):
                status = -1
        except (ValueError, KeyError, TypeError, OverflowError):
            xyz, status = (0., 0., 0.), -1
        yield Fix(event.stamp_ns, event.received_ns, xyz, receiver, status,
                  event.frame_id, initialization_only=initial_phase)


def replay_localization(rows, fixes, route, policy, path=None, origin_ns=None):
    """Reference values are intentionally NEVER used here."""
    initial = Localizer(route, replace(policy, initial_only=True), path, origin_ns)
    sparse = Localizer(route, replace(policy, initial_only=False), path, origin_ns)
    fixes = iter(fixes)
    next_fix = next(fixes, None)
    result, journal = [], []
    last_receipt = None
    for row in rows:
        tick = row['time_ns']
        batch = []
        while next_fix is not None and next_fix.received_ns <= tick:
            if last_receipt is not None and next_fix.received_ns < last_receipt:
                raise ValueError('Fixes must be in receipt order, not sorted by future source timestamps')
            last_receipt = next_fix.received_ns
            batch.append(next_fix)
            next_fix = next(fixes, None)
        plain = initial.step(tick, row['distance'], batch)
        corrected = sparse.step(tick, row['distance'], batch)
        result.append(dict(time_ns=str(tick), raw_distance=row['distance'], velocity=row['velocity'],
                           initial_only=plain, sparse=corrected))
        for mode, observer in (('initial_only', initial), ('sparse', sparse)):
            journal.extend(dict(mode=mode, applied_at_ns=str(tick), **x) for x in observer.last_decisions)
    return dict(points=result, corrections=journal,
                counts={'initial_only': dict(initial.counts), 'sparse': dict(sparse.counts)})


def localization_for(settings, payload):
    bag, run_id = payload.get('bag'), payload.get('run')
    allowed(bag)
    route = Route(payload.get('route'))
    if len(payload['route']['source']) > 1000:
        raise ValueError('Route source description too long')
    period = payload.get('period_s', 30.)
    if not finite(period) or not 1 <= period <= 600:
        raise ValueError('Fix interval must be 1..600 s (experimental scenario, not an organizer guarantee)')
    receiver = payload.get('receiver', 'master')
    if receiver not in ('master', 'rover'):
        raise ValueError('Select one fixed receiver')
    keys = {'gain', 'max_age_s', 'lateral_gate_m', 'innovation_gate_m', 'max_correction_m', 'ambiguity_margin_m', 'initial_window_s'}
    changes = payload.get('policy', {})
    if not isinstance(changes, dict) or not set(changes) <= keys:
        raise ValueError('Unknown correction policy field')
    policy = Policy(**changes)
    rows, config, pin, prediction_sha = load_prediction(settings, run_id, bag)
    from .service import manifest
    record = next((r for r in manifest(settings)['bags'] if r['id'] == bag), None)
    if record is None or record['sha256'] != pin['sha256']:
        raise ValueError('Dataset does not match pinned development input')
    from ..data import read_bag
    events = read_bag(record, settings.cache, settings.dataset/'tram_vehicle_msgs/msg')
    fixes = selected_fixes(events, receiver, period, record['start_ns'], route, policy.initial_window_s)
    start = time.monotonic()
    try:
        result = replay_localization(rows, fixes, route, policy, payload.get('path') or None, record['start_ns'])
    finally:
        events.close()
    result.update(schema=1, run=run_id, bag=bag, baseline_or_candidate=config['estimator'],
        bag_sha256=pin['sha256'], prediction_sha256=prediction_sha, route_sha256=route.sha256,
        receiver=receiver, period_s=period, policy=asdict(policy), role='reused_development',
        organizer_contract_status=contract()['status'], elapsed_s=time.monotonic()-start,
        coordinate_frame='ENU', route_origin_wgs84=route.origin, reference_point='base_link',
        height_reference=route.document['height_reference'],
        orientation_assumption='route tangent heading/pitch, roll=0',
        implementation_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
            for name in ('research/localization.py', 'research/route.py', 'research/models.py',
                         'research/contract.json', 'web/research_api.py')},
        scorer_target_status='UNCONFIRMED_XY_XYZ_BASE_LINK_ANTENNA',
        official_xyz_score=None, reference_not_used=True,
        note='Only the route offset changes. No speed/raw-distance reset. Not GNSS-independent evaluation.')
    identity = uuid.uuid4().hex
    folder = inside(settings.runs, 'research_localization/'+identity)
    folder.mkdir(parents=True, exist_ok=False)
    result['artifact_run'] = 'research_localization/'+identity
    result['total_points'] = len(result['points'])
    # Unique artifact; the existing run/CSV/config and its score are not rewritten.
    (folder/'result.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    (folder/'route.json').write_text(json.dumps(payload['route'], ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    # Display-only decimation retains correction/status transitions. Full artifact stays intact.
    n = len(result['points']); keep = set(range(0, n, max(1, math.ceil(n/3000))))
    stamps = [int(p['time_ns']) for p in result['points']]
    for row in result['corrections']:
        i = bisect_left(stamps, int(row['applied_at_ns']))
        keep.update(k for k in (i-1, i, i+1) if 0 <= k < n)
    for i in range(1, n):
        if any(result['points'][i][key]['status'] != result['points'][i-1][key]['status']
               or result['points'][i][key]['segment_id'] != result['points'][i-1][key]['segment_id']
               for key in ('initial_only', 'sparse')):
            keep.update((i-1, i))
    if n:
        keep.add(n-1)
    result['points'] = [result['points'][i] for i in sorted(keep)]
    return result


async def bounded_json(request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 2_500_000:
            raise HTTPException(413, 'Research request exceeds 2.5 MB')
    try:
        def invalid_constant(value):
            raise ValueError('Non-finite JSON constant: '+value)
        def finite_float(text):
            value = float(text)
            if not math.isfinite(value):
                raise ValueError('Non-finite JSON number')
            return value
        value = json.loads(raw, parse_constant=invalid_constant, parse_float=finite_float)
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        return value
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise HTTPException(400, str(exc)) from exc


def router_for(settings, store):
    replay_lock = Lock()
    router = APIRouter(prefix='/api/v1/research', tags=['research'])
    @router.get('/contract')
    def get_contract():
        return dict(contract(), model_id=MODEL_ID, route_file_bundled=False)

    @router.get('/page', include_in_schema=False)
    def page():
        return FileResponse(Path(__file__).with_name('research_page.html'),
                            headers={'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'none'"})

    @router.get('/page.js', include_in_schema=False)
    def script():
        return FileResponse(Path(__file__).with_name('research_page.js'), media_type='text/javascript')

    @router.post('/enqueue', status_code=202)
    async def enqueue(request: Request):
        payload = await bounded_json(request)
        bags = payload.get('bags')
        if not isinstance(bags, list) or not bags or len(bags) > 17 or not all(isinstance(b, str) for b in bags) or len(set(bags)) != len(bags):
            raise HTTPException(400, 'Select distinct development bags')
        hashes = [allowed(bag)['sha256'] for bag in bags]
        if len(hashes) != len(set(hashes)):
            raise ValueError('Select one canonical bag per database hash')
        from .service import manifest, validate_request
        data = await run_in_threadpool(manifest, settings)
        records = {r['id']: r for r in data['bags']}
        for bag in bags:
            if bag not in records or records[bag]['sha256'] != allowed(bag)['sha256']:
                raise ValueError('Development source checksum mismatch')
        job = dict(name='v8 / traction-only · development', bags=bags,
                   models=[{'id': 'hack_v8'}, {'id': MODEL_ID}], seed=42,
                   faults=payload.get('faults', []), quality={})
        await run_in_threadpool(validate_request, settings, 'experiment', job)
        return store.create('experiment', job)

    @router.post('/compare')
    async def compare(request: Request):
        p = await bounded_json(request)
        return await run_in_threadpool(scope_comparison, settings, p.get('baseline'), p.get('candidate'), p.get('bags'), p.get('vehicle', '30618'))

    @router.post('/localize')
    async def localize(request: Request):
        p = await bounded_json(request)
        if not replay_lock.acquire(blocking=False):
            raise HTTPException(409, 'A localization replay is already running')
        try:
            return await run_in_threadpool(localization_for, settings, p)
        finally:
            replay_lock.release()
    return router
