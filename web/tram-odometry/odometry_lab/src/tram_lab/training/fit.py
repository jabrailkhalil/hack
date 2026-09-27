"""Fit only to agreeing, fresh training WHEELS. Never read GNSS or true speed."""
import json
from pathlib import Path
import numpy as np
from tram_lab.hypotheses.common import DEFAULT_MODEL
from tram_lab.replay import replay
from .synthetic import BASE_NS, DURATION_S, TRAIN_SEEDS, generate, held_inputs


def robust_ridge(x, y, prior, penalty):
    norm = np.maximum(np.sqrt(np.mean(x*x, axis=0)), 1e-5)
    scaled = x / norm
    coefficient = np.asarray(prior) * norm
    initial = coefficient.copy()
    for _ in range(5):
        residual = y - scaled @ coefficient
        weight = np.minimum(1., .2 / np.maximum(np.abs(residual), 1e-8))
        a = scaled.T @ (weight[:, None] * scaled) / len(x) + penalty * np.eye(x.shape[1])
        b = scaled.T @ (weight * y) / len(x) + penalty * initial
        coefficient = np.linalg.solve(a, b)
    return coefficient / norm


def fit_training(trips, learn_residual=False):
    """trips = iterable[(unique_id, events, start_ns, end_ns)] from TRAIN only."""
    source = trips if callable(trips) else lambda: iter(trips)
    rows, targets, ids = [], [], []
    for identity, events, start_ns, end_ns in source():
        ids.append(identity)
        grid = np.arange(start_ns, end_ns + 1, 50_000_000, dtype=np.int64)
        samples, fresh = held_inputs(events, grid)
        v = np.mean(samples[:, :2], axis=1)
        u = samples[:, 2]
        reliable = fresh & np.isfinite(samples).all(axis=1) & (np.abs(samples[:, 0] - samples[:, 1]) < .15)
        feature = np.zeros((len(grid), 5))
        drive_plus = drive_minus = 0.
        for i in range(len(grid)):
            if not np.isfinite(v[i]) or not np.isfinite(u[i]):
                continue
            tau = .3 if u[i] < 0 else .45
            alpha = -np.expm1(-.05 / tau)
            drive_plus += alpha * (max(u[i], 0) / (1 + v[i] / 18) - drive_plus)
            drive_minus += alpha * (min(u[i], 0) * np.tanh(v[i] / .3) - drive_minus)
            feature[i] = [drive_plus, drive_minus, -np.tanh(v[i] / .3), -v[i], -v[i]*v[i]]
        # A forward 0.5-second target is confined to this training trip.
        h = 10
        target = (v[h:] - v[:-h]) / .5
        valid = reliable[:-h] & reliable[h:] & (v[:-h] > .5) & np.isfinite(target) & (np.abs(target) < 3)
        selected = np.flatnonzero(valid)
        if len(selected) > 10000:
            selected = selected[np.linspace(0, len(selected)-1, 10000).astype(int)]
        rows.append(feature[:-h][selected])
        targets.append(target[selected])
    x, y = np.vstack(rows), np.concatenate(targets)
    if len(y) < 100:
        raise ValueError("insufficient reliable TRAIN wheel labels")
    coefficient = robust_ridge(x, y, DEFAULT_MODEL["coefficients"], .03)
    coefficient = np.clip(coefficient, [0.2, .2, 0, 0, 0], [5, 6, .5, .1, .01])
    model = {**DEFAULT_MODEL, "coefficients": coefficient.tolist()}
    result = {"dynamics": model, "residual": None, "training_ids": ids,
              "label_source": "fresh agreeing TRAIN wheels only; no GNSS and no synthetic truth",
              "dynamic_training_rows": len(np.concatenate(targets)), "residual_training_rows": 0,
              "target_horizon_s": .5, "test_used_for_fit": False}
    if not learn_residual:
        return result
    from tram_lab.hypotheses.concept_b import AdaptiveEKF
    residual_x, residual_y = [], []
    for identity, events, start_ns, end_ns in source():
        grid = np.arange(start_ns, end_ns + 1, 50_000_000, dtype=np.int64)
        samples, fresh = held_inputs(events, grid)
        v = np.mean(samples[:, :2], axis=1)
        reliable = fresh & np.isfinite(samples).all(axis=1) & (np.abs(samples[:, 0] - samples[:, 1]) < .15)
        estimates = list(replay(events, AdaptiveEKF({"dynamics": model}), int(grid[0]), int(grid[-1])))
        feature = np.array([e.diagnostics.get("features", [np.nan]*8) for e in estimates])
        physics = np.array([e.diagnostics.get("physics_acceleration", np.nan) for e in estimates])
        h = 10
        target = (v[h:] - v[:-h]) / .5 - physics[:-h]
        valid = reliable[:-h] & reliable[h:] & np.isfinite(feature[:-h]).all(axis=1) & np.isfinite(target) & (v[:-h] > .5)
        selected = np.flatnonzero(valid)
        if len(selected) > 10000:
            selected = selected[np.linspace(0, len(selected)-1, 10000).astype(int)]
        residual_x.append(feature[:-h][selected])
        residual_y.append(np.clip(target[selected], -.8, .8))
    x, y = np.vstack(residual_x), np.concatenate(residual_y)
    mean, scale = x.mean(axis=0), np.maximum(x.std(axis=0), .01)
    mean[0], scale[0] = 0., 1.  # retain intercept instead of centering it away
    normal = np.clip((x - mean) / scale, -8, 8)
    residual_coef = robust_ridge(normal, y, np.zeros(8), .1)
    residual = {"mean": mean.tolist(), "scale": scale.tolist(), "coef": residual_coef.tolist(), "limit_mps2": .35}
    return {"dynamics": model, "residual": residual, "training_ids": ids,
            "label_source": "fresh agreeing TRAIN wheels only; no GNSS and no synthetic truth",
            "dynamic_training_rows": len(np.concatenate(targets)), "residual_training_rows": len(y),
            "target_horizon_s": .5, "test_used_for_fit": False}


def main():
    trips = []
    for seed in TRAIN_SEEDS:
        events = generate(seed)[0]
        trips.append((f"synthetic_train_{seed}", events, BASE_NS, BASE_NS + DURATION_S * 10**9))
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--residual", action="store_true")
    args = parser.parse_args()
    model = fit_training(trips, learn_residual=args.residual)
    Path("research/model.json").write_text(json.dumps(model, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in model.items() if k != "residual"}, indent=2))

if __name__ == "__main__":
    main()
