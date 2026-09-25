"""Opt-in ROS adapter; the existing default adapter and model stay unchanged."""
import rclpy
from .node import ReserveOdometryNode
from .guarded_readout import GuardedReadoutObserver, ReadoutConfig


class GuardedOdometryNode(ReserveOdometryNode):
    def __init__(self):
        super().__init__()
        config = ReadoutConfig(
            gain=self.declare_parameter('readout.gain', 1.0).value,
            holdoff_s=self.declare_parameter('readout.holdoff_s', 0.5).value)
        # No executor has spun yet: replacing the pristine observer cannot lose
        # subscriptions or received samples. Timeline clocks/queues stay intact.
        self.timeline.observer = GuardedReadoutObserver(self.timeline.observer.c, readout=config)
        self.get_logger().info('Guarded output-only time compensation enabled; inner observer is unchanged')


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = GuardedOdometryNode()
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
