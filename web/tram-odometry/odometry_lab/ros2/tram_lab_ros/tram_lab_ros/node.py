import json
import time
from dataclasses import asdict
from pathlib import Path
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import QoSProfile, ReliabilityPolicy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from tram_vehicle_msgs.msg import VelocitySensor, DriverControllerCommand
from tram_lab.adapters import event_from_message, trace_safe
from tram_lab.estimators import make_estimator
from tram_lab.replay import EventClock
from tram_lab.types import FRONT, REAR, COMMAND


class OdometryNode(Node):
    def __init__(self):
        super().__init__("tram_lab_estimator")
        self.declare_parameter("estimator", "mean")
        self.declare_parameter("wheel_scale", 1 / 3.6)
        self.declare_parameter("stale_after_s", .5)
        self.declare_parameter("period_ms", 50.0)
        self.declare_parameter("trace_path", "")
        self.config = {"name": self.get_parameter("estimator").value,
                       "wheel_scale": self.get_parameter("wheel_scale").value,
                       "stale_after_s": self.get_parameter("stale_after_s").value}
        self.period_ns = round(self.get_parameter("period_ms").value * 1e6)
        if self.period_ns <= 0:
            raise ValueError("period_ms must be positive")
        self.estimator = make_estimator(self.config)
        self.engine = None
        self.current_ns = None
        self.sequence = 0
        self.epoch = -1
        self.pending_wall = []
        trace_path = self.get_parameter("trace_path").value
        if trace_path:
            Path(trace_path).parent.mkdir(parents=True, exist_ok=True)
        self.trace = open(trace_path, "w", encoding="utf-8", buffering=1) if trace_path else None
        qos_in = QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.create_subscription(VelocitySensor, FRONT, lambda m: self.receive(FRONT, m), qos_in)
        self.create_subscription(VelocitySensor, REAR, lambda m: self.receive(REAR, m), qos_in)
        self.create_subscription(DriverControllerCommand, COMMAND, lambda m: self.receive(COMMAND, m), qos_in)
        self.create_subscription(Clock, "/clock", self.on_clock, qos_in)
        self.velocity_pub = self.create_publisher(VelocitySensor, "/result/velocity", 100)
        self.position_pub = self.create_publisher(Odometry, "/result/position", 100)
        self.diagnostics_pub = self.create_publisher(DiagnosticArray, "/diagnostics", 100)
        self.record({"kind": "config", "config": self.config, "period_ns": self.period_ns})

    def record(self, item):
        if self.trace:
            self.trace.write(json.dumps(trace_safe(item), allow_nan=False, separators=(",", ":")) + "\n")

    def on_clock(self, message):
        now = message.clock.sec * 1_000_000_000 + message.clock.nanosec
        if self.engine is None and now == 0:
            return
        if self.current_ns is None or now < self.current_ns:
            self.epoch += 1
            self.estimator.reset(self.config)
            self.engine = EventClock(self.estimator, now, self.period_ns)
            self.pending_wall.clear()
        self.current_ns = now
        self.record({"kind": "clock", "time_ns": now, "epoch": self.epoch})
        # Defer the boundary itself until the next clock message, so callbacks
        # arriving at that timestamp can be processed before prediction.
        for estimate in self.engine.advance(now, inclusive=False):
            self.publish(estimate)

    def receive(self, topic, message):
        if self.engine is None:
            return
        event = event_from_message(topic, message, self.current_ns, self.sequence)
        self.sequence += 1
        self.record({"kind": "event", "event": asdict(event), "epoch": self.epoch})
        for estimate in self.engine.push(event):
            self.publish(estimate)
        # Bound the pending list even if a required wheel never arrives.
        self.pending_wall.append((event.received_ns, time.perf_counter_ns()))
        self.pending_wall = self.pending_wall[-1000:]

    def publish(self, estimate):
        self.record({"kind": "estimate", "estimate": asdict(estimate), "epoch": self.epoch})
        if estimate.velocity is None:
            return
        started = time.perf_counter_ns()
        velocity = VelocitySensor()
        velocity.header.stamp.sec, velocity.header.stamp.nanosec = divmod(estimate.time_ns, 1_000_000_000)
        velocity.header.frame_id = "base_link"
        velocity.velocity = estimate.velocity
        position = Odometry()
        position.header.stamp = velocity.header.stamp
        position.header.frame_id = "track_relative"
        position.child_frame_id = "base_link"
        position.pose.pose.position.x = estimate.distance
        position.pose.pose.orientation.w = 1.0
        position.twist.twist.linear.x = estimate.velocity
        # Baselines do not estimate covariance; explicitly conservative placeholders.
        for i in range(6):
            position.pose.covariance[i * 6 + i] = 1e6
            position.twist.covariance[i * 6 + i] = 1e6
        self.velocity_pub.publish(velocity)
        self.position_pub.publish(position)
        now = time.perf_counter_ns()
        latency = [(now - wall) / 1e6 for stamp, wall in self.pending_wall if stamp <= estimate.time_ns]
        self.pending_wall = [(stamp, wall) for stamp, wall in self.pending_wall if stamp > estimate.time_ns]
        diagnostics = DiagnosticArray()
        diagnostics.header = velocity.header
        status = DiagnosticStatus()
        status.name = "tram_lab/odometry"
        status.hardware_id = "baseline"
        status.level = DiagnosticStatus.WARN if estimate.status == "stale" else DiagnosticStatus.OK
        status.message = estimate.status + "; longitudinal relative path; uncalibrated covariance"
        status.values = [KeyValue(key=str(k), value=str(v)) for k, v in estimate.diagnostics.items()]
        diagnostics.status = [status]
        self.diagnostics_pub.publish(diagnostics)
        self.record({"kind": "publication", "time_ns": estimate.time_ns, "epoch": self.epoch,
                     "input_to_publication_ms": latency, "publish_work_ms": (now - started) / 1e6})

    def destroy_node(self):
        if self.trace:
            self.trace.close()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = OdometryNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
