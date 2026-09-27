import csv
import json
import math
from pathlib import Path
import numpy as np
from ..metrics import path_series
from .geometry import cached_geometry, project
from .service import manifest
from .storage import safe_path


def clean(value):
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    return value


def envelope_indices(columns, segments, limit=5000):
    """Keep every gap boundary and per-bucket extrema of every displayed series."""
    length = len(segments)
    if length <= limit:
        return np.arange(length)
    keep = {0, length - 1}
    for values in [np.asarray(c) for c in columns]:
        valid = np.isfinite(values)
        changes = np.flatnonzero(valid[1:] != valid[:-1])
        keep.update(changes.tolist()); keep.update((changes+1).tolist())
    changes = np.flatnonzero(np.diff(segments) != 0)
    keep.update(changes.tolist()); keep.update((changes+1).tolist())
    buckets = max(1, limit // (2*max(1, len(columns))))
    for a, b in zip(np.linspace(0, length, buckets+1, dtype=int)[:-1], np.linspace(0, length, buckets+1, dtype=int)[1:]):
        for values in columns:
            local = np.asarray(values)[a:b]
            if np.isfinite(local).any():
                keep.add(a+int(np.nanargmin(local))); keep.add(a+int(np.nanargmax(local)))
    return np.asarray(sorted(keep), dtype=int)


def record_for(settings, bag):
    record = next((r for r in manifest(settings)['bags'] if r['id'] == bag), None)
    if not record:
        raise ValueError('Поездка отсутствует в датасете')
    return record


def geometry_for(settings, bag):
    record = record_for(settings, bag)
    return cached_geometry(json.dumps(record, sort_keys=True), str(settings.cache), str(settings.dataset / 'tram_vehicle_msgs/msg'))


def load_series(settings, run_id, bag, limit=5000):
    folder = safe_path(settings.runs, run_id)
    prediction = safe_path(folder / 'bags', bag + '/predictions.csv')
    provenance = json.loads((folder / 'provenance.json').read_text(encoding='utf-8'))
    record = record_for(settings, bag)
    expected = next((r['sha256'] for r in provenance['bags'] if r['id'] == bag), None)
    if expected != record['sha256']:
        raise ValueError('Хеш поездки не совпадает с сохранённым запуском')
    with prediction.open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    def numbers(key):
        return np.asarray([float(r[key]) if r.get(key) else np.nan for r in rows])
    time_ns = np.asarray([int(r['time_ns']) for r in rows], dtype=np.int64)
    t = (time_ns - record['start_ns']) / 1e9
    velocity, distance, reference = (numbers(k) for k in ('velocity_mps', 'distance_m', 'reference_mps'))
    matched = np.asarray([r['matched'].lower() == 'true' for r in rows])
    quality_matched = np.asarray([r.get('quality_matched', r['matched']).lower() == 'true' for r in rows])
    paths = path_series(time_ns, distance, reference, matched)
    # Even without reference, an available model's accumulated distance is useful.
    plot_distance = paths['local_distance'] if matched.any() else distance
    geo = geometry_for(settings, bag)
    predicted, actual, geo_segment = project(geo, t, distance)
    error = np.where(matched, velocity-reference, np.nan)
    diagnostics = {}
    diag_file = prediction.parent / 'diagnostics.npz'
    if diag_file.exists():
        with np.load(diag_file, allow_pickle=False) as archive:
            diagnostics = {k: archive[k] for k in archive.files if archive[k].shape == t.shape}
    columns = [velocity, reference, distance, error, paths['local_distance'], paths['reference_distance'], paths['distance_error']]
    # Map validity boundaries must survive decimation too.
    columns.extend([predicted[:, 0], actual[:, 0]])
    indices = envelope_indices(columns + list(diagnostics.values()), paths['path_segment'], limit)
    resources_file = folder / 'resources.json'
    resources = next((r for r in json.loads(resources_file.read_text()) if r.get('bag') == bag), {}) if resources_file.exists() else {}
    payload = dict(run_id=run_id, bag=bag, total_points=len(t), t=t[indices],
                   plot_distance=plot_distance[indices], resources=resources,
                   time_ns=[str(x) for x in time_ns[indices]], velocity=velocity[indices],
                   reference=reference[indices], error=error[indices], distance=distance[indices],
                   predicted_position=predicted[indices], actual_position=actual[indices],
                   matched=matched[indices].tolist(), quality_matched=quality_matched[indices].tolist(),
                   geo_segment=geo_segment[indices], status=[rows[i]['status'] for i in indices],
                   diagnostics={k: v[indices] for k, v in diagnostics.items()},
                   metrics=json.loads((prediction.parent / 'metrics.json').read_text(encoding='utf-8')),
                   **{k: v[indices] for k, v in paths.items()})
    return clean(payload)
