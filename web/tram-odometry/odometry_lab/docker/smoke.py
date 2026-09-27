"""Offline-network ROS integration: synthetic clock + two real bag playbacks."""
import json
import math
import signal
import subprocess
import time
from collections import defaultdict, deque
from dataclasses import asdict
from pathlib import Path
import numpy as np
import psutil
import rclpy
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from nav_msgs.msg import Odometry
from diagnostic_msgs.msg import DiagnosticArray
from tram_vehicle_msgs.msg import VelocitySensor, DriverControllerCommand
from tram_lab.types import Event, FRONT, REAR, COMMAND
from tram_lab.data import build_manifest, materialize_bag, write_json
from tram_lab.estimators import make_estimator
from tram_lab.replay import EventClock

OUT = Path("/artifacts")
OUT.mkdir(parents=True, exist_ok=True)


class Probe(Node):
    def __init__(self):
        super().__init__("tram_lab_smoke_probe")
        self.clock = self.create_publisher(Clock, "/clock", 100)
        self.front = self.create_publisher(VelocitySensor, FRONT, 100)
        self.rear = self.create_publisher(VelocitySensor, REAR, 100)
        self.command = self.create_publisher(DriverControllerCommand, COMMAND, 100)
        self.velocity, self.position, self.diagnostics = [], [], []
        self.create_subscription(VelocitySensor, "/result/velocity", self.velocity.append, 1000)
        self.create_subscription(Odometry, "/result/position", self.position.append, 1000)
        self.create_subscription(DiagnosticArray, "/diagnostics", self.diagnostics.append, 1000)

    def spin_for(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=min(.005, max(0, end - time.monotonic())))

    def tick(self, ns, raw=36.0, wheels=True):
        clock = Clock()
        clock.clock.sec, clock.clock.nanosec = divmod(ns, 10**9)
        self.clock.publish(clock)
        self.spin_for(.003)
        if wheels:
            wheel = VelocitySensor()
            wheel.header.stamp = clock.clock
            wheel.header.frame_id = "base_link"
            wheel.velocity = float(raw)
            self.front.publish(wheel); self.rear.publish(wheel)
            command = DriverControllerCommand()
            command.header.stamp = clock.clock
            command.position = 1
            self.command.publish(command)
        self.spin_for(.007)


def start_node(name):
    log = (OUT / f"{name}.log").open("w")
    process = subprocess.Popen(["ros2", "run", "tram_lab_ros", "estimator", "--ros-args", "-p", "use_sim_time:=true", "-p", f"trace_path:={OUT / (name + '.jsonl')}"], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    return process, log


def stop_node(process, log):
    import os
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)
    log.close()


def check_trace(path):
    config, engine, current = None, None, None
    expected, actual, latencies = [], [], []
    epochs, rollbacks = set(), []
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            kind = row["kind"]
            if kind == "config":
                config = row
                estimator = make_estimator(config["config"])
            elif kind == "clock":
                now = row["time_ns"]
                epochs.add(row["epoch"])
                if current is None or now < current:
                    if current is not None:
                        rollbacks.append(now - current)
                    estimator.reset(config["config"])
                    engine = EventClock(estimator, now, config["period_ns"])
                current = now
                expected.extend(asdict(e) for e in engine.advance(now, inclusive=False))
            elif kind == "event":
                expected.extend(asdict(e) for e in engine.push(Event(**row["event"])))
            elif kind == "estimate":
                actual.append(row["estimate"])
            elif kind == "publication":
                latencies.extend(row["input_to_publication_ms"])
    assert expected == actual, "ROS callback trace differs from offline core replay"
    assert sum(e["velocity"] is not None for e in actual) > 10
    return {"exact_core_parity": True, "prediction_count": len(actual), "epochs": len(epochs),
            "clock_rollbacks_ns": rollbacks,
            "input_to_publication_ms_p95": float(np.quantile(latencies, .95)) if latencies else None,
            "input_to_publication_ms_p99": float(np.quantile(latencies, .99)) if latencies else None,
            "input_to_publication_ms_max": max(latencies) if latencies else None,
            "latency_sample_count": len(latencies)}


def validate_outputs(probe):
    assert len(probe.velocity) > 10 and len(probe.position) > 10
    positions = defaultdict(deque)
    for m in probe.position:
        positions[m.header.stamp.sec * 10**9 + m.header.stamp.nanosec].append(m)
    matched = 0
    for msg in probe.velocity:
        ns = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
        assert ns > 0 and math.isfinite(msg.velocity)
        if not positions[ns]:
            continue
        p = positions[ns].popleft()
        assert all(math.isfinite(x) for x in [p.pose.pose.position.x, p.pose.pose.position.y, p.pose.pose.position.z, p.twist.twist.linear.x])
        assert p.header.frame_id == "track_relative" and p.child_frame_id == "base_link"
        assert p.pose.pose.position.y == 0 and p.pose.pose.position.z == 0
        assert p.pose.pose.orientation.w == 1
        assert abs(p.twist.twist.linear.x - msg.velocity) < 1e-12
        matched += 1
    assert matched / len(probe.velocity) > .95
    return {"velocity_messages": len(probe.velocity), "position_messages": len(probe.position), "matched_topics": matched}


def main():
    rclpy.init()
    probe = Probe()
    process = log = None
    result = {"status": "running", "network": "disabled by host runner", "memory_limit_mib": 512, "cpu_limit": 2}
    try:
        process, log = start_node("synthetic")
        probe.spin_for(2)
        assert process.poll() is None, "estimator did not start"
        names = dict(probe.get_topic_names_and_types())
        assert names.get("/result/velocity") == ["tram_vehicle_msgs/msg/VelocitySensor"]
        assert names.get("/result/position") == ["nav_msgs/msg/Odometry"]
        base = 1_700_000_000_000_000_000
        for i in range(161):
            probe.tick(base + i * 10_000_000, raw=float("nan") if i == 70 else 36, wheels=i % 10 == 0)
        probe.spin_for(.15)
        paused_count = len(probe.velocity)
        probe.spin_for(.3)
        assert len(probe.velocity) == paused_count, "publishes while /clock paused"
        for i in range(161, 221):
            probe.tick(base + i * 10_000_000, raw=36, wheels=i % 10 == 0)
        first_epoch = list(probe.velocity)
        assert all(abs(m.velocity - 10) < 1e-12 for m in first_epoch)
        assert any(any(v.key == "rejected_values" and int(v.value) >= 2 for v in status.values) for msg in probe.diagnostics for status in msg.status)
        times = np.array([m.header.stamp.sec * 10**9 + m.header.stamp.nanosec for m in first_epoch], dtype=np.int64)
        assert np.all(np.diff(times) == 50_000_000), "not exactly 20 Hz on simulated timeline"
        reset_position_start = len(probe.position)
        probe.tick(base, raw=18)
        for i in range(1, 111):
            probe.tick(base + i * 10_000_000, raw=18, wheels=i % 10 == 0)
        probe.spin_for(.1)
        reset_positions = probe.position[reset_position_start:]
        assert reset_positions and abs(reset_positions[0].pose.pose.position.x) < 1e-12, "path did not reset"
        assert all(abs(m.twist.twist.linear.x - 5) < 1e-12 for m in reset_positions)
        child_rss = sum(p.memory_info().rss for p in [psutil.Process(process.pid), *psutil.Process(process.pid).children(recursive=True)])
        result["synthetic"] = {"pause_verified": True, "rollback_verified": True, "nonfinite_inputs_rejected": True, "frequency_hz": 20,
                               "wall_latency_includes_deliberate_clock_pause": True, "adapter_process_tree_rss_bytes": child_rss,
                               **validate_outputs(probe)}
        stop_node(process, log); process = log = None
        result["synthetic"].update(check_trace(OUT / "synthetic.jsonl"))
        assert result["synthetic"]["input_to_publication_ms_p95"] <= 100
        # Real CDR messages and rosbag2 transport, twice to verify replay resets.
        manifest = build_manifest("/dataset", OUT / "cache")
        record = next(r for r in manifest["bags"] if r["id"] == "30618_0d865417")
        bag = materialize_bag(record, OUT / "cache")
        probe.velocity.clear(); probe.position.clear()
        process, log = start_node("real_bag")
        probe.spin_for(2)
        episode_counts = []
        for episode in range(2):
            before_count = len(probe.velocity)
            with (OUT / f"player-{episode}.log").open("w") as player_log:
                player = subprocess.Popen(["ros2", "bag", "play", str(bag), "--clock", "100", "--rate", "2", "--topics", FRONT, REAR, COMMAND], stdout=player_log, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 30
                while player.poll() is None and time.monotonic() < deadline:
                    probe.spin_for(.05)
                if player.poll() is None:
                    player.terminate(); player.wait(timeout=5)
                    raise AssertionError("rosbag player timeout")
                assert player.returncode == 0, "rosbag playback failed"
            probe.spin_for(.2)
            episode_counts.append(len(probe.velocity) - before_count)
            assert episode_counts[-1] > 100, "missing continuous output during real bag playback"
        result["real_bag"] = validate_outputs(probe)
        result["real_bag"]["playback_message_counts"] = episode_counts
        stop_node(process, log); process = log = None
        result["real_bag"].update(check_trace(OUT / "real_bag.jsonl"))
        # Humble Player may emit a small backward clock step while starting.
        # Verify the actual full-trip rewind, not a fixed count of all clock resets.
        assert any(delta < -record["duration_ns"] // 2 for delta in result["real_bag"]["clock_rollbacks_ns"])
        result["status"] = "passed"
    except BaseException as exc:
        result["status"] = "failed"
        result["error"] = repr(exc)
        raise
    finally:
        if process is not None:
            stop_node(process, log)
        write_json(OUT / "smoke.json", result)
        probe.destroy_node(); rclpy.shutdown()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
