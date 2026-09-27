import csv
import hashlib
import importlib.metadata
import json
import platform
import threading
import time
from pathlib import Path
import numpy as np
import psutil
import yaml
from .data import build_manifest, read_bag, write_json
from .estimators import make_estimator
from .faults import inject_faults
from .metrics import evaluate, error_metrics
from .replay import replay
from .reporting import write_predictions, plot_bag, write_report


class ResourceMonitor:
    def __enter__(self):
        self.process = psutil.Process()
        self.rss_peak = self.process.memory_info().rss
        self.before_cpu = sum(self.process.cpu_times()[:2])
        self.started = time.perf_counter()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)
        self.thread.start()
        return self

    def _sample(self):
        while not self.stop.wait(.02):
            self.rss_peak = max(self.rss_peak, self.process.memory_info().rss)

    def __exit__(self, *_):
        self.stop.set(); self.thread.join()
        self.rss_peak = max(self.rss_peak, self.process.memory_info().rss)
        self.result = {"wall_seconds": time.perf_counter() - self.started,
                       "process_cpu_seconds": sum(self.process.cpu_times()[:2]) - self.before_cpu,
                       "peak_process_rss_bytes_sampled": self.rss_peak, "rss_sample_period_ms": 20,
                       "kind": "offline_process_not_ros_latency"}


def load_config(path, overrides=None):
    path = Path(path).resolve()
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    allowed = {"dataset", "cache", "output", "msg_dir", "bags", "split_file", "subset", "estimator", "period_ms", "seed", "faults", "quality", "tolerance_ms", "plots"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"unknown config keys: {sorted(unknown)}")
    for key in ("dataset", "cache", "output", "msg_dir", "split_file"):
        if key in config:
            config[key] = str((path.parent / config[key]).resolve())
    for key, value in (overrides or {}).items():
        if value is not None:
            config[key] = str(Path(value).resolve()) if key in {"dataset", "cache", "output", "msg_dir"} else value
    config.setdefault("dataset", str((path.parent / "../../dataset").resolve()))
    config.setdefault("cache", str((path.parent / "../.cache").resolve()))
    config.setdefault("estimator", {"name": "mean", "wheel_scale": 1 / 3.6, "stale_after_s": .5})
    config.setdefault("period_ms", 50)
    config.setdefault("seed", 0)
    config.setdefault("faults", [])
    config.setdefault("quality", {})
    config.setdefault("tolerance_ms", 50)
    config.setdefault("plots", True)
    if config["period_ms"] <= 0 or config["tolerance_ms"] < 0:
        raise ValueError("period must be positive and tolerance nonnegative")
    if not isinstance(config["estimator"], dict):
        raise ValueError("estimator must be a mapping")
    return config


def select_records(manifest, bags=None, split_file=None, subset=None):
    by_id = {r["id"]: r for r in manifest["bags"]}
    if split_file:
        split = json.loads(Path(split_file).read_text(encoding="utf-8"))
        if subset not in {"train", "validation", "test"}:
            raise ValueError("subset must be train, validation or test")
        if bags:
            raise ValueError("choose explicit bags OR a split subset")
        bags = split["splits"][subset]
        for bag in bags:
            if bag not in by_id or split["bag_hashes"][bag] != by_id[bag]["sha256"]:
                raise ValueError("split manifest does not match dataset content")
    if not bags:
        bags = [r["id"] for r in manifest["bags"] if r["id"] == r["canonical_id"]] if not split_file else []
    if not bags:
        raise ValueError("selection is empty")
    selected, seen = [], set()
    for bag in bags:
        if bag not in by_id:
            raise ValueError(f"unknown bag: {bag}")
        record = by_id[bag]
        if record["sha256"] in seen:
            raise ValueError("selection contains duplicate bag content")
        seen.add(record["sha256"])
        selected.append(record)
    return selected


def msg_directory(config):
    dataset = Path(config["dataset"])
    base = dataset.parent if dataset.suffix == ".zip" else dataset
    return Path(config.get("msg_dir", base / "tram_vehicle_msgs" / "msg"))


def run_experiment(config, progress=print):
    output = Path(config["output"])
    if output.exists():
        raise FileExistsError(f"refusing to overwrite run: {output}")
    manifest = build_manifest(config["dataset"], config["cache"])
    records = select_records(manifest, config.get("bags"), config.get("split_file"), config.get("subset"))
    output.mkdir(parents=True)
    write_json(output / "config.json", config)
    (output / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=True, allow_unicode=True), encoding="utf-8")
    versions = {package: importlib.metadata.version(package) for package in ["tram-odometry-lab", "numpy", "rosbags", "PyYAML", "matplotlib", "psutil"]}
    from .catalog import source_digest
    write_json(output / "provenance.json", {"versions": versions, "python": platform.python_version(), "platform": platform.platform(),
        "core_source_sha256": source_digest(), "seed": config["seed"], "bags": [{"id": r["id"], "sha256": r["sha256"]} for r in records],
        "reference_policy": "master-if-present-else-rover; nearest-header; no implicit cleaning", "position_semantics": "relative longitudinal distance, not ENU"})
    summaries, resources, pooled_errors = [], [], []
    for record in records:
        progress(f"Running {record['id']} ({record['duration_ns']/1e9:.1f} s)")
        folder = output / "bags" / record["id"]
        folder.mkdir(parents=True)
        with ResourceMonitor() as monitor:
            events = list(read_bag(record, config["cache"], msg_directory(config)))
            corrupted = list(inject_faults(events, config["faults"], config["seed"], record["start_ns"])) if config["faults"] else events
            estimator = make_estimator(config["estimator"])
            started = time.perf_counter()
            estimates = list(replay(corrupted, estimator, record["start_ns"], record["end_ns"], round(config["period_ms"] * 1e6)))
            replay_seconds = time.perf_counter() - started
            metrics, details = evaluate(estimates, events, round(config["tolerance_ms"] * 1e6), config["quality"], record["start_ns"])
            pooled_errors.append(details["error"][details["matched"]])
            write_predictions(folder / "predictions.csv", estimates, details)
            keys = sorted({k for e in estimates for k, value in e.diagnostics.items()
                           if isinstance(value, (int, float)) and not isinstance(value, bool)})
            np.savez_compressed(folder / 'diagnostics.npz', **{
                k: np.asarray([e.diagnostics.get(k, np.nan) for e in estimates], dtype=float) for k in keys})
            write_json(folder / "metrics.json", metrics)
            if config["plots"]:
                plot_bag(folder, record["id"], estimates, corrupted, details, record["start_ns"], config["estimator"].get("wheel_scale", 1 / 3.6))
        resources.append({"bag": record["id"], **monitor.result, "replay_wall_seconds": replay_seconds,
                          "replay_bag_seconds_per_wall_second": record["duration_ns"] / 1e9 / replay_seconds})
        summaries.append({"id": record["id"], "sha256": record["sha256"], "metrics": metrics})
    total_ticks = sum(r["metrics"]["ticks"] for r in summaries)
    bag_rmse = [r["metrics"]["speed"]["rmse_mps"] for r in summaries if r["metrics"]["speed"]["count"]]
    aggregate = {"bags": len(summaries), "pooled_speed": error_metrics(np.concatenate(pooled_errors)),
                 "macro_mean_bag_rmse_mps": float(np.mean(bag_rmse)) if bag_rmse else None,
                 "coverage": sum(r["metrics"]["matched"] for r in summaries) / total_ticks if total_ticks else 0,
                 "prediction_coverage": sum(r["metrics"]["available"] for r in summaries) / total_ticks if total_ticks else 0,
                 "bags_without_velocity_reference": sum(r["metrics"]["reference"]["source"] is None for r in summaries)}
    summary = {"aggregate": aggregate, "bags": summaries}
    write_json(output / "metrics.json", summary)
    write_json(output / "resources.json", resources)
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        columns = ["bag", "rmse_mps", "mae_mps", "bias_mps", "p95_abs_mps", "coverage", "stale_count"]
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n"); writer.writeheader()
        for bag in summaries:
            m = bag["metrics"]
            writer.writerow({"bag": bag["id"], **{k: m["speed"][k] for k in columns[1:5]}, "coverage": m["coverage"], "stale_count": m["stale_count"]})
    write_report(output, summary, config)
    progress(f"Report: {output / 'report.html'}")
    return summary
