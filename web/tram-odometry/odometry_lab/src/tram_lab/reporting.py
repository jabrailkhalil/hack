import csv
import html
import json
from pathlib import Path
import numpy as np


def write_predictions(path, estimates, details):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["time_ns", "velocity_mps", "distance_m", "status", "age_s", "measurement_age_s", "clock_anomalies", "future_header", "reference_mps", "matched", "quality_matched", "error_mps"])
        for i, e in enumerate(estimates):
            match = bool(details["matched"][i])
            writer.writerow([e.time_ns, e.velocity, e.distance, e.status, e.diagnostics.get("age_s"), e.diagnostics.get("measurement_age_s"),
                             e.diagnostics.get("clock_anomalies", 0), e.diagnostics.get("future_header", False),
                             float(details["reference"][i]) if np.isfinite(details["reference"][i]) else "", match, bool(details["quality_matched"][i]),
                             float(details["error"][i]) if match else ""])


def plot_bag(folder, bag_id, estimates, events, details, start_ns, wheel_scale):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .types import FRONT, REAR, COMMAND, MASTER_VEL, ROVER_VEL
    from .metrics import reference_series
    folder = Path(folder)
    t = (details["time_ns"] - start_ns) / 1e9
    fig, axes = plt.subplots(5, 1, figsize=(13, 14), sharex=True, constrained_layout=True)
    for topic, label in [(FRONT, "front"), (REAR, "rear")]:
        samples = [e for e in events if e.topic == topic]
        x = np.asarray([e.stamp_ns for e in samples], dtype=np.int64)
        y = np.asarray([e.data["velocity"] * wheel_scale for e in samples])
        axes[0].plot((x - start_ns) / 1e9, y, alpha=.35, linewidth=.7, label=label)
    for topic, label in [(MASTER_VEL, "GNSS master"), (ROVER_VEL, "GNSS rover")]:
        x, y = reference_series(events, topic)
        axes[0].plot((x - start_ns) / 1e9, y, linewidth=.7, alpha=.65, label=label)
    axes[0].plot(t, details["velocity"], linewidth=1, label="estimate")
    axes[0].set_ylabel("Speed, m/s")
    axes[0].legend(ncol=5, fontsize=8)
    axes[1].plot(t, details["distance"], label="relative longitudinal distance")
    axes[1].set_ylabel("Distance, m")
    axes[1].legend()
    axes[2].plot(t, np.where(details["matched"], details["error"], np.nan), linewidth=.7)
    axes[2].axhline(0, color="grey", linewidth=.7)
    axes[2].set_ylabel("Speed error, m/s")
    cmd = [e for e in events if e.topic == COMMAND]
    axes[3].step([(e.received_ns - start_ns) / 1e9 for e in cmd], [e.data["position"] for e in cmd], where="post")
    axes[3].set_ylabel("Controller notch")
    axes[4].plot(t, [e.diagnostics.get("age_s", np.nan) for e in estimates], label="receipt age")
    axes[4].plot(t, [e.diagnostics.get("measurement_age_s", np.nan) for e in estimates], label="header age", alpha=.6)
    axes[4].set_ylabel("Input age, s")
    axes[4].set_xlabel("Seconds from bag start")
    axes[4].legend()
    for axis in axes:
        axis.grid(alpha=.2)
    fig.suptitle(bag_id + " — diagnostic baselines; relative path, not ENU")
    fig.savefig(folder / "signals.png", dpi=110)
    plt.close(fig)


def write_report(output, summary, config):
    rows = []
    for bag in summary["bags"]:
        speed = bag["metrics"]["speed"]
        bag_id = bag["id"]
        rmse = "N/A" if speed["rmse_mps"] is None else f"{speed['rmse_mps']:.5f}"
        graph = f'<a href="bags/{html.escape(bag_id)}/signals.png">graphs</a> · ' if (Path(output) / "bags" / bag_id / "signals.png").exists() else ''
        rows.append(f'<tr><td>{html.escape(bag_id)}</td><td>{rmse}</td><td>{bag["metrics"]["coverage"]:.1%}</td><td>{bag["metrics"]["stale_count"]}</td><td>{graph}<a href="bags/{html.escape(bag_id)}/predictions.csv">CSV</a></td></tr>')
    content = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Odometry lab report</title>
<style>body{{font:16px system-ui;max-width:1200px;margin:40px auto;padding:0 20px;background:#f8fafc;color:#17233b}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{padding:12px;border-bottom:1px solid #dbe2eb;text-align:left}}pre{{white-space:pre-wrap;background:white;padding:18px;border-radius:8px}}a{{color:#075fca}}</style>
<h1>Odometry lab</h1><p>Базовая оценка: <b>{html.escape(str(config['estimator']))}</b></p>
<p>GNSS используется только для офлайн-оценки. Путь — относительная продольная координата, не ENU.
Ошибки пути считаются отдельно на непрерывных сопоставленных интервалах. N/A означает отсутствие эталона.
Показатели исполнения в resources.json относятся к офлайн-процессу, а не к задержке ROS.</p>
<h2>Сводка</h2><pre>{html.escape(json.dumps(summary['aggregate'],ensure_ascii=False,indent=2))}</pre>
<table><thead><tr><th>Bag</th><th>RMSE, м/с</th><th>Покрытие GNSS</th><th>Stale ticks</th><th>Результаты</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Конфигурация</h2><pre>{html.escape(json.dumps(config,ensure_ascii=False,indent=2))}</pre>
<p><a href="metrics.json">Полные метрики</a> · <a href="resources.json">Ресурсы</a> · <a href="provenance.json">Происхождение данных</a></p></html>'''
    (Path(output) / "report.html").write_text(content, encoding="utf-8")


def compare_runs(run_dirs, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for run in run_dirs:
        run = Path(run)
        metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
        for bag in metrics["bags"]:
            m = bag["metrics"]
            rows.append({"run": run.name, "bag": bag["id"], "sha256": bag["sha256"], **m["speed"], "coverage": m["coverage"], "stale_count": m["stale_count"]})
    if not rows:
        raise ValueError("no results to compare")
    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    from .data import write_json
    write_json(output / "comparison.json", rows)
    columns = list(rows[0])
    body = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(row[k]))}</td>' for k in columns) + '</tr>' for row in rows)
    (output / "report.html").write_text('<!doctype html><meta charset="utf-8"><title>Comparison</title><h1>Run comparison</h1><p>Compare rows with matching bag SHA-256; differing coverage or reference policies can change metrics.</p><table border="1"><tr>' + ''.join(f'<th>{k}</th>' for k in columns) + '</tr>' + body + '</table>', encoding="utf-8")
    return rows
