"""ROS 2 Humble adapter for the organizer's exact message contract."""
import math
import time
from collections import OrderedDict
from dataclasses import fields
import rclpy
from rclpy.node import Node
from rclpy.clock import Clock, ClockType
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_srvs.srv import Trigger
from tram_vehicle_msgs.msg import VelocitySensor, DriverControllerCommand
from nav_msgs.msg import Odometry
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from .core import Config, Observer, Sample
from .timeline import Timeline
from .route import Route


class ReserveOdometryNode(Node):
    def __init__(self):
        super().__init__('reserve_odometry')
        defaults = Config()
        params = {}
        for field in fields(Config):
            params[field.name] = self.declare_parameter('model.' + field.name,
                                                        getattr(defaults, field.name)).value
        self.declare_parameter('rate_hz', 20.0)
        self.declare_parameter('alignment_delay_s', .06)
        self.declare_parameter('clock_mode', 'input_stamp')
        self.trace_timing = self.declare_parameter('trace_timing', False).value
        # Explicit empirical dataset conversion; README says m/s, measured ratio ~3.6.
        self.scale_front = self.declare_parameter('front_scale', 1.0 / 3.6).value
        self.scale_rear = self.declare_parameter('rear_scale', 1.0 / 3.6).value
        self.declare_parameter('route_csv', '')
        self.route_s0 = self.declare_parameter('route_s0', 0.0).value
        self.route_frame = self.declare_parameter('route_frame', 'map').value
        self.clock_mode = self.get_parameter('clock_mode').value
        if self.clock_mode not in ('input_stamp', 'ros_clock'):
            raise ValueError('clock_mode must be input_stamp or ros_clock')
        if any(not math.isfinite(x) or x <= 0 for x in (self.scale_front, self.scale_rear)):
            raise ValueError('Wheel scale must be finite and positive')
        if not math.isfinite(self.route_s0):
            raise ValueError('route_s0 must be finite')
        self.timeline = Timeline(Observer(Config(**params)),
                                 self.get_parameter('rate_hz').value,
                                 self.get_parameter('alignment_delay_s').value)
        route_path = self.get_parameter('route_csv').value
        self.route = Route.from_csv(route_path) if route_path else None
        if self.route is None:
            self.get_logger().warning('RELATIVE 1D POSITION: no map/heading. This is NOT an ENU trajectory.')
        self.get_logger().warning('Wheel scale defaults to 1/3.6 from measured dataset audit; verify organizer units.')
        qos = QoSProfile(depth=64, reliability=ReliabilityPolicy.BEST_EFFORT,
                         history=HistoryPolicy.KEEP_LAST)
        self.create_subscription(DriverControllerCommand, '/vehicle/driver_position_cmd', self.command, qos)
        self.create_subscription(VelocitySensor, '/vehicle/front_bogie_velocity', self.front, qos)
        self.create_subscription(VelocitySensor, '/vehicle/rear_bogie_velocity', self.rear, qos)
        self.velocity_pub = self.create_publisher(VelocitySensor, '/result/velocity', 10)
        self.position_pub = self.create_publisher(Odometry, '/result/position', 10)
        self.diag_pub = self.create_publisher(DiagnosticArray, '/result/diagnostics', 10)
        self.timing_pub = self.create_publisher(DiagnosticArray, '/result/timing', 64) if self.trace_timing else None
        self.create_service(Trigger, '~/reset', self.reset_service)
        self.bad_messages = 0
        self.total_outputs = 0
        self.last_diag = 0.0
        self.last_input_receipt = None
        self.last_publish_stamp = None
        self.origin_ns = None
        self.last_ros_ns = None
        self.clock_resets_total = 0
        self.receipts = [OrderedDict(), OrderedDict(), OrderedDict()]
        self.route_ok = True
        # Use a steady timer even if /clock pauses; never advance the estimator on wall time.
        self.steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self.create_timer(.01, self.tick, clock=self.steady_clock)

    def receive(self, channel, msg, value):
        received = time.perf_counter_ns()
        try:
            stamp = msg.header.stamp
            absolute_ns = stamp.sec * 1000000000 + stamp.nanosec
            limit = 1.000001 if channel == 0 else self.timeline.observer.c.max_speed_mps
            if stamp.nanosec >= 1000000000 or absolute_ns <= 0:
                raise ValueError('Invalid/zero absolute source timestamp')
            if not math.isfinite(value) or abs(value) > limit:
                raise ValueError('Nonfinite/out-of-range input')
            if self.origin_ns is None:
                self.origin_ns = absolute_ns
            # Subtract integer origin BEFORE float conversion; no epoch precision loss.
            sample = Sample((absolute_ns - self.origin_ns) / 1e9, float(value))
            if self.timeline.ingest(channel, sample):
                self.last_input_receipt = received / 1e9
                if self.trace_timing:
                    entries = self.receipts[channel]
                    entries[sample.t] = received
                    while len(entries) > 256:
                        entries.popitem(last=False)
            else:
                self.bad_messages += 1
        except (ValueError, TypeError, OverflowError):
            self.bad_messages += 1

    def command(self, msg):
        self.receive(0, msg, float(msg.position) / 15.0)

    def front(self, msg):
        self.receive(1, msg, msg.velocity * self.scale_front)

    def rear(self, msg):
        self.receive(2, msg, msg.velocity * self.scale_rear)

    def reset_service(self, request, response):
        self.timeline.reset()
        self.last_publish_stamp = None
        self.origin_ns = None
        self.last_ros_ns = None
        self.receipts = [OrderedDict(), OrderedDict(), OrderedDict()]
        response.success = True
        response.message = 'Observer reset; new relative origin. Restart for each independent bag.'
        return response

    def tick(self):
        started = time.perf_counter()
        now = None
        if self.clock_mode == 'ros_clock':
            absolute_now = self.get_clock().now().nanoseconds
            if absolute_now <= 0 or self.origin_ns is None:
                return
            if self.last_ros_ns is not None and absolute_now < self.last_ros_ns:
                self.timeline.reset()
                self.origin_ns = None
                self.receipts = [OrderedDict(), OrderedDict(), OrderedDict()]
                self.clock_resets_total += 1
                self.last_ros_ns = absolute_now
                return
            self.last_ros_ns = absolute_now
            now = (absolute_now - self.origin_ns) / 1e9
        for estimate, held in self.timeline.advance(now):
            if estimate.mode != 'WAITING_FOR_INITIALIZATION':
                self.publish(estimate, held)
        elapsed = (time.perf_counter() - started) * 1000
        if time.monotonic() - self.last_diag >= 1.0:
            self.diagnostics(elapsed)
            self.last_diag = time.monotonic()

    def publish(self, e, held):
        ns = self.origin_ns + int(round(e.t * 1e9))
        vel = VelocitySensor()
        vel.header.stamp.sec, vel.header.stamp.nanosec = divmod(ns, 1000000000)
        vel.header.frame_id = 'base_link'
        vel.velocity = float(e.v)
        odom = Odometry()
        # Header is a mutable Python object; avoid changing the velocity header frame.
        from copy import deepcopy
        odom.header = deepcopy(vel.header)
        odom.header.frame_id = self.route_frame if self.route else 'odom_path_1d'
        odom.child_frame_id = 'base_link'
        xyz, quat = (e.s, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)
        route_ok = True
        if self.route:
            try:
                xyz, quat = self.route.at(self.route_s0 + e.s)
            except ValueError:
                # Never emit a fabricated/clamped map position past the known route.
                route_ok = False
                self.bad_messages += 1
        odom.pose.pose.position.x, odom.pose.pose.position.y, odom.pose.pose.position.z = xyz
        q = odom.pose.pose.orientation
        q.x, q.y, q.z, q.w = quat
        odom.twist.twist.linear.x = float(e.v)
        for i in (0, 7, 14, 21, 28, 35):
            odom.pose.covariance[i] = 1e6
            odom.twist.covariance[i] = 1e6
        odom.pose.covariance[0] = float(e.variance_s) if not self.route else 1e6
        odom.twist.covariance[0] = float(e.variance_v)
        self.route_ok = route_ok
        before_publish = time.perf_counter_ns()
        self.velocity_pub.publish(vel)
        if route_ok:
            self.position_pub.publish(odom)
        self.total_outputs += 1
        self.last_publish_stamp = e.t
        if self.timing_pub is not None:
            timing = DiagnosticArray()
            timing.header = deepcopy(vel.header)
            status = DiagnosticStatus(name='reserve_odometry/timing', hardware_id='tram')
            values = {'publish_mono_ns': before_publish, 'source_ns': ns,
                      'mode': e.mode, 'front_status': e.front_status, 'rear_status': e.rear_status}
            for i, name in enumerate(('command', 'front', 'rear')):
                sample = held[i]
                if sample is not None:
                    values[name + '_stamp_ns'] = self.origin_ns + int(round(sample.t * 1e9))
                    values[name + '_receipt_ns'] = self.receipts[i].get(sample.t, 0)
            status.values = [KeyValue(key=k, value=str(v)) for k, v in values.items()]
            timing.status = [status]
            self.timing_pub.publish(timing)

    def diagnostics(self, callback_ms):
        msg = DiagnosticArray()
        msg.header.stamp = self.get_clock().now().to_msg()
        d = DiagnosticStatus()
        d.name = 'reserve_odometry/observer'
        d.hardware_id = 'tram'
        e = self.timeline.observer.last_estimate
        d.level = DiagnosticStatus.WARN
        d.message = e.mode if e else 'WAITING_FOR_INPUT'
        if e and e.mode in ('FUSED', 'STOPPED', 'SINGLE_WHEEL') and self.route:
            d.level = DiagnosticStatus.OK
        input_age = time.perf_counter() - self.last_input_receipt if self.last_input_receipt is not None else None
        if input_age is None or input_age > 1.0:
            d.level = DiagnosticStatus.WARN
            d.message = 'INPUT_STALE_OR_PAUSED'
        if not self.route_ok:
            d.level = DiagnosticStatus.ERROR
            d.message = 'OUTSIDE_AUTHORIZED_ROUTE'
        values = dict(callback_compute_ms=callback_ms, outputs=self.total_outputs,
                      input_receipt_age_s=input_age, source_origin_ns=self.origin_ns,
                      invalid_messages=self.bad_messages, buffer_dropped=self.timeline.dropped,
                      backward_clock_resets=self.timeline.resets + self.clock_resets_total,
                      forward_gap_catchups=self.timeline.catchup_events,
                      position_mode='route' if self.route else 'relative_1d')
        if e:
            values.update(front_status=e.front_status, rear_status=e.rear_status,
                          command_stale=e.command_stale, disturbance=e.disturbance,
                          source_stamp_relative_s=e.t, variance_v=e.variance_v)
        d.values = [KeyValue(key=k, value=str(v)) for k, v in values.items()]
        msg.status = [d]
        self.diag_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = ReserveOdometryNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
