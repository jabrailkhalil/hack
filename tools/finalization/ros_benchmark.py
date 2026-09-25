"""Real ROS process, actual SQLite/CDR inputs, 1x receipt-order playback.

This is a test publisher, not the estimator. No GNSS is sent to the runtime.
For the long check use --seconds 0 (entire development bag). It records both
callback-to-publication and publisher-to-independent-result-subscriber latency,
including rejected/held input processing where a corresponding output exists.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sqlite3
import statistics
import subprocess
import tempfile
import time

import rclpy
from rclpy.node import Node
from rclpy.serialization import deserialize_message
from rcl_interfaces.srv import GetParameters
from diagnostic_msgs.msg import DiagnosticArray
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from tram_vehicle_msgs.msg import VelocitySensor, DriverControllerCommand

ROOT = Path(__file__).resolve().parents[2]
TOPICS = ['/vehicle/driver_position_cmd', '/vehicle/front_bogie_velocity', '/vehicle/rear_bogie_velocity']


def ns(stamp):
    return stamp.sec * 1_000_000_000 + stamp.nanosec


def summary(values):
    values = sorted(values)
    if not values:
        return {'n': 0, 'p50': None, 'p95': None, 'p99': None, 'max': None}
    def quantile(p):
        pos = (len(values) - 1) * p
        i = int(pos); j = min(i + 1, len(values) - 1)
        return values[i] + (values[j] - values[i]) * (pos - i)
    return dict(n=len(values), p50=quantile(.5), p95=quantile(.95), p99=quantile(.99), max=values[-1])


def resources(pid):
    """Sum the launcher and its live descendants, Linux /proc only."""
    queue = [pid]; seen = set(); rss = 0; cpu = 0
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            stat = Path(f'/proc/{current}/stat').read_text().rsplit(')', 1)[1].split()
            cpu += int(stat[11]) + int(stat[12])
            rss += int(stat[21]) * os.sysconf('SC_PAGE_SIZE')
            queue.extend(map(int, Path(f'/proc/{current}/task/{current}/children').read_text().split()))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    return rss, cpu / os.sysconf('SC_CLK_TCK')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bag', default='30618_0652866c')
    parser.add_argument('--seconds', type=float, default=60.)
    parser.add_argument('--clock-mode', choices=['input_stamp', 'ros_clock'], default='input_stamp')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'research/split_v3.json').read_text())
    record = next(row for row in manifest['records'] if row['bag'] == args.bag)
    if record['split'] != 'development':
        raise PermissionError('Runtime benchmark only opens pre-existing development bags')
    db = ROOT / 'dataset/data' / args.bag / (args.bag + '_0.db3')
    if hashlib.sha256(db.read_bytes()).hexdigest() != record['sha256']:
        raise ValueError('Bag checksum mismatch')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    log = tempfile.TemporaryFile(mode='w+')
    cmd = ['ros2', 'run', 'reserve_odometry', 'odometry_node', '--ros-args', '--params-file',
           str(ROOT / 'src/reserve_odometry/config/default.yaml'), '-p', 'trace_timing:=true',
           '-p', 'clock_mode:=' + args.clock_mode]
    if args.clock_mode == 'ros_clock':
        cmd += ['-p', 'use_sim_time:=true']
    process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    rclpy.init(); probe = Node('submission_benchmark_probe')
    velocities = {}; positions = {}; traces = []; diagnostic = []; sent = {}; offered = Counter()
    rss_rows = []; failures = []; start = None
    try:
        client = probe.create_client(GetParameters, '/reserve_odometry/get_parameters')
        if not client.wait_for_service(timeout_sec=20):
            raise AssertionError('Node did not start')
        request = GetParameters.Request(names=['alignment_delay_s', 'rate_hz', 'clock_mode'])
        future = client.call_async(request)
        rclpy.spin_until_future_complete(probe, future, timeout_sec=5)
        values = future.result().values
        effective = dict(alignment_delay_s=values[0].double_value, rate_hz=values[1].double_value,
                         clock_mode=values[2].string_value)
        pubs = [probe.create_publisher(DriverControllerCommand if i == 0 else VelocitySensor, topic, 64)
                for i, topic in enumerate(TOPICS)]
        clock_pub = probe.create_publisher(Clock, '/clock', 10) if args.clock_mode == 'ros_clock' else None
        def velocity(msg):
            if not math.isfinite(msg.velocity) or msg.header.frame_id != 'base_link':
                failures.append('bad_velocity')
            key = ns(msg.header.stamp)
            if key in velocities:
                failures.append('duplicate_velocity_stamp')
            velocities[key] = (time.perf_counter_ns(), msg.velocity)
        def position(msg):
            xyz = msg.pose.pose.position
            if msg.header.frame_id != 'odom_path_1d' or msg.child_frame_id != 'base_link':
                failures.append('bad_frame')
            if not all(math.isfinite(x) for x in (xyz.x, xyz.y, xyz.z)):
                failures.append('nonfinite_position')
            if abs(msg.pose.pose.orientation.w - 1.) > 1e-9:
                failures.append('bad_quaternion')
            key = ns(msg.header.stamp)
            positions[key] = (time.perf_counter_ns(), xyz.x)
        probe.create_subscription(VelocitySensor, '/result/velocity', velocity, 128)
        probe.create_subscription(Odometry, '/result/position', position, 128)
        probe.create_subscription(DiagnosticArray, '/result/timing',
            lambda msg: traces.append((ns(msg.header.stamp), {v.key: v.value for v in msg.status[0].values})), 128)
        probe.create_subscription(DiagnosticArray, '/result/diagnostics',
            lambda msg: diagnostic.append({v.key: v.value for v in msg.status[0].values}), 10)
        ready = time.monotonic()
        while time.monotonic() - ready < 1.5:
            rclpy.spin_once(probe, timeout_sec=.01)
        assert all(pub.get_subscription_count() >= 1 for pub in pubs), 'Input discovery incomplete'
        with sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True) as con:
            query = ('SELECT m.timestamp,t.name,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                     'WHERE t.name IN (?,?,?) ORDER BY m.timestamp,m.id')
            first, last = con.execute('SELECT MIN(timestamp),MAX(timestamp) FROM messages').fetchone()
            full_duration = (last - first) / 1e9
            duration = full_duration if args.seconds <= 0 else min(full_duration, args.seconds)
            cursor = con.execute(query, TOPICS); row = cursor.fetchone()
            start = time.perf_counter_ns(); next_resource = 0.; next_clock = 0.
            while True:
                now = time.perf_counter_ns(); elapsed = (now - start) / 1e9
                if process.poll() is not None:
                    raise AssertionError('Estimator process exited')
                if elapsed > duration + .5:
                    break
                virtual_ns = first + int(min(elapsed, duration) * 1e9)
                if clock_pub is not None and elapsed >= next_clock and elapsed <= duration:
                    msg = Clock(); msg.clock.sec, msg.clock.nanosec = divmod(virtual_ns, 1_000_000_000)
                    clock_pub.publish(msg); next_clock = elapsed + .01
                burst = 0
                while row is not None and row[0] <= virtual_ns and burst < 256:
                    received, topic, raw = row; channel = TOPICS.index(topic)
                    cls = DriverControllerCommand if channel == 0 else VelocitySensor
                    msg = deserialize_message(raw, cls); stamp = ns(msg.header.stamp)
                    send_ns = time.perf_counter_ns()
                    sent.setdefault((channel, stamp), send_ns)
                    offered[channel] += 1
                    pubs[channel].publish(msg)
                    row = cursor.fetchone(); burst += 1
                if elapsed >= next_resource:
                    rss, cpu = resources(process.pid)
                    rss_rows.append((elapsed, rss, cpu)); next_resource = elapsed + 1.
                rclpy.spin_once(probe, timeout_sec=.001)
        assert start is not None
        seen = set(); pipe_ms = []; result_ms = []; all_result_ms = []; modes = Counter()
        causal_errors = 0; stale_receipt = 0
        for stamp, trace in traces:
            modes[trace['mode']] += 1
            if stamp not in velocities or stamp not in positions:
                continue
            arrival = max(velocities[stamp][0], positions[stamp][0])
            for channel, label in enumerate(('command', 'front', 'rear')):
                input_stamp = int(trace.get(label + '_stamp_ns', 0))
                receipt = int(trace.get(label + '_receipt_ns', 0))
                if input_stamp > stamp:
                    causal_errors += 1
                key = (channel, input_stamp)
                if not receipt or key in seen:
                    continue
                seen.add(key)
                begin = sent.get(key)
                if begin is None:
                    stale_receipt += 1; continue
                publish = int(trace['publish_mono_ns'])
                if receipt > publish or arrival < receipt:
                    causal_errors += 1
                all_result_ms.append((arrival - begin) / 1e6)
                if (begin - start) / 1e9 >= 10.:
                    pipe_ms.append((publish - receipt) / 1e6)
                    result_ms.append((arrival - begin) / 1e6)
        stamps = list(velocities)
        if any(b <= a for a, b in zip(stamps, stamps[1:])):
            failures.append('nonmonotone_output_stamps')
        if set(velocities) != set(positions):
            failures.append('velocity_position_mismatch')
        reception = [row[0] for row in velocities.values()]
        source_rate = (len(stamps) - 1) * 1e9 / (stamps[-1] - stamps[0]) if len(stamps) > 1 else 0.
        wall_rate = (len(reception) - 1) * 1e9 / (reception[-1] - reception[0]) if len(reception) > 1 else 0.
        if source_rate < 10 or wall_rate < 10:
            failures.append('rate_below_10hz')
        if causal_errors:
            failures.append('causality_errors')
        last_diag = diagnostic[-1] if diagnostic else {}
        if int(last_diag.get('backward_clock_resets', 0)) != 0:
            failures.append('unexpected_position_reset')
        with args.output.with_suffix('.trace.csv').open('w', newline='') as stream:
            writer = csv.writer(stream); writer.writerow(['source_ns', 'v_mps', 's_m', 'velocity_received_ns', 'position_received_ns'])
            for stamp in stamps:
                if stamp in positions:
                    writer.writerow([stamp, velocities[stamp][1], positions[stamp][1], velocities[stamp][0], positions[stamp][0]])
        with args.output.with_suffix('.resources.csv').open('w', newline='') as stream:
            writer = csv.writer(stream); writer.writerow(['elapsed_s', 'rss_bytes', 'cpu_seconds']); writer.writerows(rss_rows)
        initial = [r[1] for r in rss_rows if 10 <= r[0] <= 40]
        tail = [r[1] for r in rss_rows if r[0] >= max(10., duration - 30)]
        cpu_windows = [(b[2]-a[2])/(b[0]-a[0]) for a,b in zip(rss_rows,rss_rows[1:]) if b[0]>a[0]]
        result = dict(bag=args.bag, role='development', bag_sha256=record['sha256'],
            playback='1x actual rosbag SQLite record order via independent ROS publisher', full_bag=args.seconds<=0,
            record_duration_s=full_duration, measured_duration_s=duration, effective_parameters=effective,
            trace_timing_enabled=True, offered_messages=dict(offered), unique_offered=len(sent),
            unique_inputs_with_matching_result=len(seen), uncredited_inputs=len(set(sent)-seen),
            outputs=len(stamps), position_outputs=len(positions), mode_counts=dict(modes),
            source_rate_hz=source_rate, wall_rate_hz=wall_rate,
            callback_to_publish_ms_after_10s=summary(pipe_ms),
            publisher_to_both_result_subscribers_ms_after_10s=summary(result_ms),
            publisher_to_both_result_subscribers_ms_all=summary(all_result_ms),
            rss_peak_bytes=max((r[1] for r in rss_rows),default=0),
            rss_median_first_window_bytes=statistics.median(initial) if initial else None,
            rss_median_last_window_bytes=statistics.median(tail) if tail else None,
            cpu_core_equivalents=summary(cpu_windows), final_diagnostics=last_diag,
            causal_errors=causal_errors, unknown_input_receipts=stale_receipt, correctness_failures=failures,
            latency_note='First held-input processing result; source age is not transport latency. Uncredited inputs are reported, not assigned zero latency.',
            test_not_evaluated=True)
        latency = result['publisher_to_both_result_subscribers_ms_after_10s']
        result['latency_observed_within_nominal_and_peak'] = bool(latency['p95'] is not None and latency['p95'] <= 100 and result['publisher_to_both_result_subscribers_ms_all']['max'] <= 250)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
        print(json.dumps(result, indent=2), flush=True)
        assert not failures, failures
    finally:
        probe.destroy_node()
        if rclpy.ok(): rclpy.shutdown()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)
        log.seek(0); args.output.with_suffix('.node.log').write_text(log.read()); log.close()


if __name__ == '__main__':
    main()
