"""Signal helpers. Differences of int64 clocks are computed before float conversion."""
import numpy as np


def convert_units(values, scale=1 / 3.6):
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("scale must be positive and finite")
    return np.asarray(values, dtype=float) * scale


def causal_derivative(times_ns, values):
    t, v = np.asarray(times_ns, dtype=np.int64), np.asarray(values, dtype=float)
    if t.shape != v.shape:
        raise ValueError("times and values must have equal shapes")
    out = np.full(v.shape, np.nan)
    dt = np.diff(t) / 1e9
    np.divide(np.diff(v), dt, out=out[1:], where=dt > 0)
    return out


def integrate_velocity(times_ns, values, initial=0.0):
    t, v = np.asarray(times_ns, dtype=np.int64), np.asarray(values, dtype=float)
    if t.shape != v.shape or np.any(np.diff(t) < 0):
        raise ValueError("equal-length arrays and monotonic time required")
    if not np.all(np.isfinite(v)):
        raise ValueError("velocity must be finite; segment missing data explicitly")
    return initial + np.r_[0.0, np.cumsum(np.diff(t) / 1e9 * (v[1:] + v[:-1]) / 2)] if len(t) else np.array([])


def align_reference(query_ns, reference_ns, tolerance_ns=50_000_000):
    """Nearest offline reference, stable ties prefer the earlier timestamp.

    Returns original reference indices (-1 when unmatched), and absolute time deltas.
    Never use this bidirectional helper to construct online estimator inputs.
    """
    q, r = np.asarray(query_ns, dtype=np.int64), np.asarray(reference_ns, dtype=np.int64)
    if tolerance_ns < 0:
        raise ValueError("tolerance must be nonnegative")
    if len(r) == 0:
        return np.full(len(q), -1, dtype=np.int64), np.full(len(q), np.iinfo(np.int64).max, dtype=np.int64)
    order = np.argsort(r, kind="stable")
    ordered = r[order]
    hi = np.clip(np.searchsorted(ordered, q), 0, len(r) - 1)
    lo = np.maximum(hi - 1, 0)
    ix = np.where(np.abs(ordered[lo] - q) <= np.abs(ordered[hi] - q), lo, hi)
    delta = np.abs(ordered[ix] - q)
    return np.where(delta <= tolerance_ns, order[ix], -1), delta


def detect_segments(times_ns, labels):
    """Contiguous labelled intervals; caller chooses labels without hidden thresholds."""
    t, labels = np.asarray(times_ns, dtype=np.int64), np.asarray(labels)
    if len(t) != len(labels):
        raise ValueError("times and labels must have equal lengths")
    if not len(t):
        return []
    cuts = np.r_[0, np.flatnonzero(labels[1:] != labels[:-1]) + 1, len(t)]
    return [{"start_ns": int(t[a]), "end_ns": int(t[b - 1]), "label": str(labels[a]), "samples": int(b - a)} for a, b in zip(cuts[:-1], cuts[1:])]
