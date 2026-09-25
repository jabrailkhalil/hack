"""Launch the installed default in a separate process; verify actual parameters.

This supplements ros_smoke.py, whose in-process node tests Config defaults.
No numpy/scipy or dataset required. This is not an end-to-end latency benchmark.
"""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import sys
import subprocess
import tempfile
import time
import rclpy
from rclpy.node import Node
from rcl_interfaces.srv import GetParameters
from nav_msgs.msg import Odometry
from tram_vehicle_msgs.msg import VelocitySensor, DriverControllerCommand


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--params-file', type=Path)
    parser.add_argument('--expected-json', type=Path)
    parser.add_argument('--launch-file', default='odometry.launch.py')
    args = parser.parse_args(argv)
    if (args.params_file is None) != (args.expected_json is None):
        parser.error('--params-file and --expected-json must be supplied together')
    root = Path(__file__).resolve().parents[1]
    decision = json.loads((root / 'reports/research_v3/decision.json').read_text())
    selected = decision['selected']
    active = root / 'reports/research_v6/PROMOTION.json'
    promoted = json.loads(active.read_text()) if active.exists() else None
    expected_path = args.expected_json or (root / 'src/reserve_odometry/config/candidates_v3' /
                                           (selected + '.json'))
    if args.expected_json is None and promoted is not None:
        expected_path = root / promoted['profile_json']
        selected = promoted['selected']
    profile = json.loads(expected_path.read_text())
    expected = {'model.' + key: value for key, value in profile['config'].items()}
    expected.update({'readout.' + key: value for key, value in profile.get('readout', {}).items()})
    launch = ['ros2', 'launch', 'reserve_odometry', args.launch_file]
    if args.params_file:
        launch.append('params_file:=' + str(args.params_file.resolve()))
        selected = expected_path.stem
    log = tempfile.TemporaryFile(mode='w+')
    process = subprocess.Popen(launch,
                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    rclpy.init()
    probe = Node('calibrated_launch_probe')
    try:
        client = probe.create_client(GetParameters, '/reserve_odometry/get_parameters')
        if not client.wait_for_service(timeout_sec=20):
            raise AssertionError('Launched node did not expose parameter service')
        request = GetParameters.Request()
        request.names = list(expected)
        future = client.call_async(request)
        rclpy.spin_until_future_complete(probe, future, timeout_sec=5)
        assert future.done() and future.result() is not None, 'No parameter response'
        values = future.result().values
        assert len(values) == len(expected)
        for (key, wanted), actual in zip(expected.items(), values):
            assert actual.type == 3, (key, actual.type)  # PARAMETER_DOUBLE
            assert math.isclose(actual.double_value, wanted, rel_tol=1e-9, abs_tol=1e-12), (key, wanted, actual)
        velocities, positions = [], []
        probe.create_subscription(VelocitySensor, '/result/velocity', velocities.append, 64)
        probe.create_subscription(Odometry, '/result/position', positions.append, 64)
        command = probe.create_publisher(DriverControllerCommand, '/vehicle/driver_position_cmd', 10)
        wheels = [probe.create_publisher(VelocitySensor, topic, 10) for topic in (
            '/vehicle/front_bogie_velocity', '/vehicle/rear_bogie_velocity')]
        started = time.monotonic()
        next_input = started
        while time.monotonic() - started < 6.0:
            assert process.poll() is None, 'Launched node exited'
            now = time.monotonic()
            if now >= next_input:
                stamp = probe.get_clock().now().to_msg()
                msg = DriverControllerCommand()
                msg.header.stamp = stamp
                msg.position = 0
                command.publish(msg)
                for publisher in wheels:
                    wheel = VelocitySensor()
                    wheel.header.stamp = stamp
                    wheel.velocity = 18.0
                    publisher.publish(wheel)
                next_input = now + .05
            rclpy.spin_once(probe, timeout_sec=.002)
        assert len(velocities) >= 60 and len(positions) >= 60, (len(velocities), len(positions))
        stamps = [msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9 for msg in velocities]
        assert all(b > a for a, b in zip(stamps, stamps[1:]))
        rate = (len(stamps) - 1) / (stamps[-1] - stamps[0])
        assert 18 < rate < 22, rate
        assert abs(velocities[-1].velocity - 5) < .15
        assert all(math.isfinite(msg.velocity) for msg in velocities)
        assert positions[-1].pose.pose.position.x > 15
        assert positions[-1].header.frame_id == 'odom_path_1d'
        assert positions[-1].child_frame_id == 'base_link'
        subscriptions = probe.get_subscriber_names_and_types_by_node('reserve_odometry', '/')
        assert not any('gnss' in name or 'imu' in name for name, _ in subscriptions)
        print(f'CALIBRATED_LAUNCH_PASS selected={selected} verified_parameters={len(expected)} '
              f'outputs={len(velocities)} rate={rate:.3f}Hz v={velocities[-1].velocity:.6f}')
    finally:
        probe.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        log.seek(0)
        print(log.read())
        log.close()


if __name__ == '__main__':
    main()
    if len(sys.argv) == 1:
        # Exercise the new installed profile in the existing ROS/offline CI jobs.
        # Explicit v5 invocations retain their original single-profile behavior.
        from ament_index_python.packages import get_package_share_directory
        share = Path(get_package_share_directory('reserve_odometry'))
        expected = Path(__file__).resolve().parents[1] / 'src/reserve_odometry/config/time_aligned_v6.json'
        main(['--params-file', str(share / 'config/time_aligned_v6.yaml'),
              '--expected-json', str(expected)])
        # Preserve both current-main launches and additionally exercise v7.
        expected = Path(__file__).resolve().parents[1] / 'src/reserve_odometry/config/guarded_readout_v7.json'
        main(['--launch-file', 'guarded_odometry.launch.py',
              '--params-file', str(share / 'config/guarded_readout_v7.yaml'),
              '--expected-json', str(expected)])
