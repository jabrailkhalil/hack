"""Installed-node regression: alternating zero-locked wheels while slowly moving."""
import math
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import os
import rclpy
from rclpy.node import Node
from rcl_interfaces.srv import GetParameters
from rosgraph_msgs.msg import Clock
from tram_vehicle_msgs.msg import DriverControllerCommand, VelocitySensor


def check(profile):
    prefix=Path(subprocess.check_output(['ros2','pkg','prefix','reserve_odometry'],text=True).strip())
    params=prefix/'share/reserve_odometry/config'/profile
    with tempfile.TemporaryFile(mode='w+') as log:
        process=subprocess.Popen(['ros2','run','reserve_odometry','odometry_node','--ros-args',
            '--params-file',str(params),'-p','clock_mode:=ros_clock','-p','use_sim_time:=true'],
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        rclpy.init();node=Node('low_speed_lock_probe');outputs=[]
        try:
            client=node.create_client(GetParameters,'/reserve_odometry/get_parameters')
            assert client.wait_for_service(timeout_sec=20),'Node not ready'
            clock=node.create_publisher(Clock,'/clock',10)
            command=node.create_publisher(DriverControllerCommand,'/vehicle/driver_position_cmd',10)
            wheels=[node.create_publisher(VelocitySensor,name,10) for name in
                    ('/vehicle/front_bogie_velocity','/vehicle/rear_bogie_velocity')]
            node.create_subscription(VelocitySensor,'/result/velocity',outputs.append,128)
            def spin(seconds):
                end=time.monotonic()+seconds
                while time.monotonic()<end:
                    assert process.poll() is None,'Node exited'
                    rclpy.spin_once(node,timeout_sec=.002)
            spin(.5)
            for i in range(141):
                t=1000+i*.05
                msg=Clock();stamp=int(round(t*1e9));msg.clock.sec,msg.clock.nanosec=divmod(stamp,10**9)
                clock.publish(msg)
                cmd=DriverControllerCommand();cmd.header.stamp=msg.clock;cmd.position=-15 if i>=80 else 0
                command.publish(cmd)
                wheel=VelocitySensor();wheel.header.stamp=msg.clock
                wheel.velocity=0. if 20<=i<60 or i>=80 else 1.3*3.6
                wheels[i%2].publish(wheel)
                spin(.025)
            spin(.2)
            locked=[m.velocity for m in outputs if 1001.1<=m.header.stamp.sec+m.header.stamp.nanosec/1e9<1003.]
            recovery=[m.velocity for m in outputs if 1003.7<=m.header.stamp.sec+m.header.stamp.nanosec/1e9<1004.]
            assert len(locked)>=25,len(locked)
            assert min(locked)>.7,min(locked)
            assert recovery and abs(recovery[-1]-1.3)<.15,recovery
            assert outputs and abs(outputs[-1].velocity)<.05,outputs[-1].velocity
            assert all(math.isfinite(m.velocity) for m in outputs)
            print(f'LOW_SPEED_LOCK_PASS profile={profile} min_lock_v={min(locked):.6f} recovered={recovery[-1]:.6f} true_stop={outputs[-1].velocity:.6f}')
        finally:
            node.destroy_node();rclpy.shutdown()
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGINT)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
            log.seek(0);print(log.read())


if __name__=='__main__':
    for profile in ('default.yaml','adaptive_v5.yaml'):check(profile)
