"""ROS integration check, run explicitly after colcon build in Humble."""
import math
import time
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.serialization import serialize_message, deserialize_message
from tram_vehicle_msgs.msg import VelocitySensor, DriverControllerCommand
from nav_msgs.msg import Odometry
from reserve_odometry.node import ReserveOdometryNode


def main():
    rclpy.init()
    estimator = ReserveOdometryNode()
    probe = Node('reserve_odometry_smoke_probe')
    executor = SingleThreadedExecutor()
    executor.add_node(estimator)
    executor.add_node(probe)
    pubs = [probe.create_publisher(DriverControllerCommand, '/vehicle/driver_position_cmd', 10),
            probe.create_publisher(VelocitySensor, '/vehicle/front_bogie_velocity', 10),
            probe.create_publisher(VelocitySensor, '/vehicle/rear_bogie_velocity', 10)]
    velocities, positions = [], []
    probe.create_subscription(VelocitySensor, '/result/velocity', velocities.append, 10)
    probe.create_subscription(Odometry, '/result/position', positions.append, 10)
    subscriptions = probe.get_subscriber_names_and_types_by_node('reserve_odometry', '/')
    assert not any('gnss' in name or 'imu' in name for name, _ in subscriptions)
    start = time.monotonic()
    last_input = -1.0
    try:
        while time.monotonic() - start < 5.0:
            elapsed = time.monotonic() - start
            if elapsed - last_input >= .05:
                stamp = probe.get_clock().now().to_msg()
                cmd = DriverControllerCommand()
                cmd.header.stamp = stamp
                cmd.position = 1
                pubs[0].publish(cmd)
                for pub in pubs[1:]:
                    wheel = VelocitySensor()
                    wheel.header.stamp = stamp
                    wheel.header.frame_id = 'base_link'
                    wheel.velocity = 18.0  # empirical input scale -> 5 m/s
                    assert deserialize_message(serialize_message(wheel), VelocitySensor).velocity == 18
                    pub.publish(wheel)
                last_input = elapsed
            executor.spin_once(timeout_sec=.002)
        assert len(velocities) >= 50, len(velocities)
        assert len(positions) >= 50, len(positions)
        assert abs(velocities[-1].velocity - 5) < .15, velocities[-1].velocity
        assert velocities[-1].header.frame_id == 'base_link'
        stamps = [v.header.stamp.sec + v.header.stamp.nanosec * 1e-9 for v in velocities]
        assert all(b > a for a, b in zip(stamps, stamps[1:]))
        rate = (len(stamps) - 1) / (stamps[-1] - stamps[0])
        assert 18 < rate < 22, rate
        assert positions[-1].header.frame_id == 'odom_path_1d'
        assert positions[-1].child_frame_id == 'base_link'
        assert positions[-1].pose.pose.position.x > 10
        assert all(math.isfinite(v.velocity) for v in velocities)
        print(f'ROS_SMOKE_PASS outputs={len(velocities)} rate={rate:.3f}Hz v={velocities[-1].velocity:.6f}')
    finally:
        executor.shutdown()
        estimator.destroy_node()
        probe.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
