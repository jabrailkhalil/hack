"""Offline reference evaluation. This module is never imported by estimators."""
import numpy as np
from .types import MASTER_VEL, ROVER_VEL
from .signals import align_reference, integrate_velocity


def reference_series(events, topic):
    rows = [e for e in events if e.topic == topic]
    return (np.asarray([e.stamp_ns for e in rows], dtype=np.int64),
            np.asarray([np.hypot(e.data["x"], e.data["y"]) for e in rows], dtype=float))


def error_metrics(errors):
    e = np.asarray(errors, dtype=float)
    e = e[np.isfinite(e)]
    if not len(e):
        return {"count": 0, "rmse_mps": None, "mae_mps": None, "bias_mps": None, "p95_abs_mps": None}
    return {"count": int(len(e)), "rmse_mps": float(np.sqrt(np.mean(e * e))), "mae_mps": float(np.mean(np.abs(e))),
            "bias_mps": float(np.mean(e)), "p95_abs_mps": float(np.quantile(np.abs(e), .95))}


def path_series(t, distance, reference, mask, max_gap_ns=500_000_000):
    """Single source of truth for segmented path charts and metrics."""
    mask = np.asarray(mask, dtype=bool) & np.isfinite(distance) & np.isfinite(reference)
    ids = np.flatnonzero(mask)
    truth = np.full(len(t), np.nan)
    predicted = np.full(len(t), np.nan)
    segments = np.full(len(t), -1, dtype=int)
    if len(ids):
        cuts = np.r_[0, np.flatnonzero((np.diff(ids) != 1) | (np.diff(t[ids]) > max_gap_ns) | (np.diff(t[ids]) <= 0)) + 1, len(ids)]
        for segment, (a, b) in enumerate(zip(cuts[:-1], cuts[1:])):
            ix = ids[a:b]
            truth[ix] = integrate_velocity(t[ix], reference[ix])
            predicted[ix] = distance[ix] - distance[ix[0]]
            segments[ix] = segment
    return dict(reference_distance=truth, local_distance=predicted,
                distance_error=predicted-truth, path_segment=segments)


def _path_metrics(t, velocity, distance, reference, mask, max_gap_ns):
    """Reference path is integrated at matched ticks, independently in valid segments.

    Gaps are not silently bridged. Errors here concern longitudinal distance,
    not geographical GNSS position or the full trip when coverage is incomplete.
    """
    series = path_series(t, distance, reference, mask, max_gap_ns)
    ids = np.flatnonzero(series['path_segment'] >= 0)
    if not len(ids):
        return {"segments": 0, "covered_duration_s": 0.0, "reference_distance_m": 0.0, "rmse_m": None,
                "covered_end_error_sum_m": None, "covered_drift_percent": None, "full_interval_end_error_m": None}
    cuts = np.r_[0, np.flatnonzero((np.diff(ids) != 1) | (np.diff(t[ids]) > max_gap_ns) | (np.diff(t[ids]) <= 0)) + 1, len(ids)]
    errors, terminal_errors, ref_lengths, duration = [], [], [], 0.0
    for a, b in zip(cuts[:-1], cuts[1:]):
        ix = ids[a:b]
        gt = series['reference_distance'][ix]
        local = series['local_distance'][ix]
        errors.extend((local - gt).tolist())
        terminal_errors.append(float(local[-1] - gt[-1]))
        ref_lengths.append(float(gt[-1]))
        duration += (int(t[ix[-1]]) - int(t[ix[0]])) / 1e9
    length = sum(ref_lengths)
    full = len(cuts) == 2 and np.array_equal(ids, np.flatnonzero(np.isfinite(velocity)))
    return {"segments": int(len(cuts) - 1), "covered_duration_s": duration, "reference_distance_m": length,
            "rmse_m": float(np.sqrt(np.mean(np.square(errors)))),
            "max_abs_m": float(np.max(np.abs(errors))), "covered_end_error_sum_m": sum(terminal_errors),
            "covered_drift_percent": 100 * sum(terminal_errors) / length if length >= 1 else None,
            "full_interval_end_error_m": terminal_errors[0] if full else None}


def evaluate(estimates, events, tolerance_ns=50_000_000, quality=None, start_ns=None):
    quality = quality or {}
    if "max_receiver_disagreement_mps" in quality and quality["max_receiver_disagreement_mps"] < 0:
        raise ValueError("reference disagreement threshold must be nonnegative")
    t = np.asarray([e.time_ns for e in estimates], dtype=np.int64)
    v = np.asarray([e.velocity if e.velocity is not None else np.nan for e in estimates], dtype=float)
    s = np.asarray([e.distance if e.distance is not None else np.nan for e in estimates], dtype=float)
    master_t, master_v = reference_series(events, MASTER_VEL)
    rover_t, rover_v = reference_series(events, ROVER_VEL)
    source = "master" if len(master_t) else ("rover" if len(rover_t) else None)
    rt, rv = (master_t, master_v) if source == "master" else (rover_t, rover_v)
    ix, dt = align_reference(t, rt, tolerance_ns)
    reference = np.full(len(t), np.nan)
    matched = ix >= 0
    reference[matched] = rv[ix[matched]]
    valid = np.isfinite(v)
    mask = valid & matched & np.isfinite(reference)
    errors = v - reference
    mi, _ = align_reference(master_t, rover_t, tolerance_ns)
    both = (mi >= 0) & np.isfinite(master_v)
    disagreement = np.abs(master_v[both] - rover_v[mi[both]])
    disagreement = disagreement[np.isfinite(disagreement)]
    reference_info = {"source": source, "master_samples": int(len(master_t)), "rover_samples": int(len(rover_t)),
        "master_backward_headers": int(np.sum(np.diff(master_t) < 0)), "rover_backward_headers": int(np.sum(np.diff(rover_t) < 0)),
        "fix_unknown_covariance_samples": sum(e.topic.endswith("/fix") and e.data.get("covariance_type") == 0 for e in events),
        "master_nonfinite": int(np.sum(~np.isfinite(master_v))), "rover_nonfinite": int(np.sum(~np.isfinite(rover_v))),
        "master_zero_samples": int(np.sum(master_v == 0)), "rover_zero_samples": int(np.sum(rover_v == 0)),
        "receiver_pairs": int(len(disagreement)), "receiver_disagreement_p95_mps": float(np.quantile(disagreement, .95)) if len(disagreement) else None,
        "receiver_disagreement_max_mps": float(np.max(disagreement)) if len(disagreement) else None}
    finite_stamps = t[valid]
    gaps = np.diff(finite_stamps) / 1e9
    metrics = {"reference": reference_info, "ticks": len(t), "available": int(valid.sum()), "matched": int(mask.sum()),
        "coverage": float(mask.mean()) if len(t) else 0.0,
        "prediction_coverage": float(valid.mean()) if len(t) else 0.0,
        "stale_count": sum(e.status == "stale" for e in estimates),
        "speed": error_metrics(errors[mask]),
        "path": _path_metrics(t, v, s, reference, mask, 500_000_000),
        "publication": {"mean_hz": float((len(finite_stamps) - 1) * 1e9 / (int(finite_stamps[-1]) - int(finite_stamps[0]))) if len(finite_stamps) > 1 and finite_stamps[-1] > finite_stamps[0] else None,
                        "max_gap_s": float(np.max(gaps)) if len(gaps) else None}}
    cleaned_mask = mask.copy()
    if quality:
        if "max_receiver_disagreement_mps" in quality:
            alt_t, alt_v = (rover_t, rover_v) if source == "master" else (master_t, master_v)
            alt_ix, _ = align_reference(t, alt_t, tolerance_ns)
            alt = np.full(len(t), np.nan)
            ok = alt_ix >= 0
            alt[ok] = alt_v[alt_ix[ok]]
            cleaned_mask &= np.isfinite(alt) & (np.abs(alt - reference) <= quality["max_receiver_disagreement_mps"])
        origin = start_ns if start_ns is not None else (int(t[0]) if len(t) else 0)
        for interval in quality.get("exclude_intervals_s", []):
            if len(interval) != 2 or interval[1] <= interval[0]:
                raise ValueError("quality intervals must be [start_s, end_s]")
            relative = (t - origin) / 1e9
            cleaned_mask &= ~((relative >= interval[0]) & (relative < interval[1]))
        metrics["explicit_quality_mask"] = {"rules": quality, "excluded": int(mask.sum() - cleaned_mask.sum()),
            "coverage": float(cleaned_mask.mean()) if len(t) else 0.0, "speed": error_metrics(errors[cleaned_mask]),
            "path": _path_metrics(t, v, s, reference, cleaned_mask, 500_000_000)}
    details = {"time_ns": t, "velocity": v, "distance": s, "reference": reference, "matched": mask,
               "quality_matched": cleaned_mask, "error": errors, "match_delta_ns": dt}
    return metrics, details


def compute_metrics(estimates, events, **kwargs):
    return evaluate(estimates, events, **kwargs)[0]
