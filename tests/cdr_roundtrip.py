"""Cross-check the offline decoder against actual ROS Humble serialization."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from export_bags import decode
from rclpy.serialization import serialize_message
from tram_vehicle_msgs.msg import VelocitySensor, DriverControllerCommand
from geometry_msgs.msg import TwistStamped
from sensor_msgs.msg import NavSatFix

for frame in ('', 'base_link', 'map_with_long_frame_id'):
    for cls, typ in ((VelocitySensor,'tram_vehicle_msgs/msg/VelocitySensor'),
                     (DriverControllerCommand,'tram_vehicle_msgs/msg/DriverControllerCommand'),
                     (TwistStamped,'geometry_msgs/msg/TwistStamped'),
                     (NavSatFix,'sensor_msgs/msg/NavSatFix')):
        msg=cls()
        msg.header.stamp.sec=123
        msg.header.stamp.nanosec=456789
        msg.header.frame_id=frame
        if cls is VelocitySensor: msg.velocity=12.5
        if cls is DriverControllerCommand: msg.position=-7
        if cls is TwistStamped:
            msg.twist.linear.x=4.0
            msg.twist.linear.y=3.0
        if cls is NavSatFix:
            msg.latitude=55.7
            msg.longitude=37.6
            msg.altitude=150.0
            msg.status.status=-1
            msg.position_covariance[0]=2.0
        stamp, values=decode(serialize_message(msg),typ)
        assert stamp==123000456789
        if cls is VelocitySensor: assert values[0]==12.5
        if cls is DriverControllerCommand: assert values[0]==-7
        if cls is TwistStamped: assert values[:3]==(4.0,3.0,0.0) or values[:3]==[4.0,3.0,0.0]
        if cls is NavSatFix:
            assert values[:3]==[55.7,37.6,150.0]
            assert values[3:]==[-1,2.0]
print('CDR_ROUNDTRIP_PASS 4 types x 3 header lengths')
