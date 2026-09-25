"""Installed ROS node: asynchronous wheels, all-input dropout, pause and seek.
Simulated clock advances faster than wall time; this is NOT a latency benchmark.
"""
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
from nav_msgs.msg import Odometry
from diagnostic_msgs.msg import DiagnosticArray
from rosgraph_msgs.msg import Clock
from tram_vehicle_msgs.msg import VelocitySensor, DriverControllerCommand


def main():
    root=Path(__file__).resolve().parents[1]
    log=tempfile.TemporaryFile(mode='w+')
    proc=subprocess.Popen(['ros2','run','reserve_odometry','odometry_node','--ros-args','--params-file',
        str(root/'src/reserve_odometry/config/default.yaml'),'-p','clock_mode:=ros_clock','-p','use_sim_time:=true'],
        stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    rclpy.init();p=Node('final_fault_probe');positions=[];velocities=[];diagnostic=[]
    try:
        reset=p.create_client(Trigger,'/reserve_odometry/reset')
        assert reset.wait_for_service(timeout_sec=20),'Node not ready'
        cp=p.create_publisher(Clock,'/clock',10)
        command=p.create_publisher(DriverControllerCommand,'/vehicle/driver_position_cmd',10)
        wheels=[p.create_publisher(VelocitySensor,topic,10) for topic in ('/vehicle/front_bogie_velocity','/vehicle/rear_bogie_velocity')]
        p.create_subscription(Odometry,'/result/position',positions.append,128)
        p.create_subscription(VelocitySensor,'/result/velocity',velocities.append,128)
        p.create_subscription(DiagnosticArray,'/result/diagnostics',diagnostic.append,10)
        def spin(duration):
            until=time.monotonic()+duration
            while time.monotonic()<until:
                assert proc.poll() is None,'Estimator died'
                rclpy.spin_once(p,timeout_sec=.002)
        def publish(t,i,with_inputs=True):
            stamp=int(round(t*1e9));c=Clock();c.clock.sec,c.clock.nanosec=divmod(stamp,1_000_000_000);cp.publish(c)
            if with_inputs:
                msg=DriverControllerCommand();msg.header.stamp=c.clock;msg.position=0
                if i==280:msg.position=31
                command.publish(msg)
                if not 80<=i<180:
                    w=VelocitySensor();w.header.stamp=c.clock;w.velocity=float('nan') if i==281 else 18.
                    wheels[i%2].publish(w)
            spin(.02)
        spin(1.0)
        before_dropout=after_dropout=None
        for i in range(321):
            publish(1000+i*.05,i,not 180<=i<240)
            if i==179:before_dropout=len(positions)
            if i==239:after_dropout=len(positions)
        spin(.15)
        assert len(positions)>250,len(positions)
        assert after_dropout-before_dropout>40,(before_dropout,after_dropout)
        assert abs(velocities[-1].velocity-5)<.2,velocities[-1].velocity
        assert all(math.isfinite(v.velocity) for v in velocities)
        assert positions[-1].pose.pose.position.x>65
        count=len(positions);s=positions[-1].pose.pose.position.x
        spin(.4)
        assert len(positions)==count,(count,len(positions))
        assert positions[-1].pose.pose.position.x==s
        jump=Clock();jump.clock.sec=1015;jump.clock.nanosec=500_000_000;cp.publish(jump);spin(.12)
        start=len(positions)
        for i in range(21):publish(1015.55+i*.05,400+i)
        spin(.15)
        assert len(positions)>start
        assert positions[start].pose.pose.position.x<1.,positions[start].pose.pose.position.x
        assert positions[-1].pose.pose.position.x<7.
        print(f'ROS_FAULT_PASS outputs={len(positions)} dropout_outputs={after_dropout-before_dropout} pause_no_motion=true short_backward_seek_reset=true')
    finally:
        p.destroy_node()
        if rclpy.ok():rclpy.shutdown()
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGINT)
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
        log.seek(0);print(log.read());log.close()

if __name__=='__main__':main()
