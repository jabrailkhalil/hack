"""Launch installed active/explicit profiles and verify real parameters."""
import argparse,json,math,os,signal,subprocess,tempfile,time
from pathlib import Path
import rclpy
from rclpy.node import Node
from rcl_interfaces.srv import GetParameters
from nav_msgs.msg import Odometry
from tram_vehicle_msgs.msg import VelocitySensor,DriverControllerCommand

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--params-file',type=Path);p.add_argument('--expected-json',type=Path)
    p.add_argument('--launch-file',default='odometry.launch.py')
    a=p.parse_args()
    if (a.params_file is None)!=(a.expected_json is None):p.error('params and expected must be paired')
    root=Path(__file__).resolve().parents[1]
    expected_path=a.expected_json or root/'src/reserve_odometry/config/guarded_readout_v7.json'
    profile=json.loads(expected_path.read_text()); selected=profile.get('name',expected_path.stem)
    expected={'model.'+k:v for k,v in profile['config'].items()}
    expected.update({'readout.'+k:v for k,v in profile.get('readout',{}).items()})
    launch=['ros2','launch','reserve_odometry',a.launch_file]
    if a.params_file:launch.append('params_file:='+str(a.params_file.resolve()))
    log=tempfile.TemporaryFile(mode='w+');proc=subprocess.Popen(launch,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    rclpy.init();node=Node('calibrated_launch_probe')
    try:
        client=node.create_client(GetParameters,'/reserve_odometry/get_parameters');assert client.wait_for_service(timeout_sec=20)
        req=GetParameters.Request();req.names=list(expected);future=client.call_async(req);rclpy.spin_until_future_complete(node,future,timeout_sec=5)
        assert future.done() and future.result() is not None
        for (key,wanted),actual in zip(expected.items(),future.result().values):
            assert actual.type==3,(key,actual.type);assert math.isclose(actual.double_value,wanted,rel_tol=1e-9,abs_tol=1e-12),(key,wanted,actual)
        velocities=[];positions=[]
        node.create_subscription(VelocitySensor,'/result/velocity',velocities.append,64)
        node.create_subscription(Odometry,'/result/position',positions.append,64)
        command=node.create_publisher(DriverControllerCommand,'/vehicle/driver_position_cmd',10)
        wheels=[node.create_publisher(VelocitySensor,t,10) for t in ('/vehicle/front_bogie_velocity','/vehicle/rear_bogie_velocity')]
        start=time.monotonic();next_input=start
        while time.monotonic()-start<6:
            assert proc.poll() is None
            now=time.monotonic()
            if now>=next_input:
                stamp=node.get_clock().now().to_msg();cmd=DriverControllerCommand();cmd.header.stamp=stamp;cmd.position=0;command.publish(cmd)
                for pub in wheels:
                    w=VelocitySensor();w.header.stamp=stamp;w.velocity=18.;pub.publish(w)
                next_input=now+.05
            rclpy.spin_once(node,timeout_sec=.002)
        assert len(velocities)>=60 and len(positions)>=60
        stamps=[x.header.stamp.sec+x.header.stamp.nanosec*1e-9 for x in velocities]
        assert all(b>a for a,b in zip(stamps,stamps[1:]));rate=(len(stamps)-1)/(stamps[-1]-stamps[0]);assert 18<rate<22
        assert abs(velocities[-1].velocity-5)<.15 and all(math.isfinite(x.velocity) for x in velocities)
        assert positions[-1].pose.pose.position.x>15 and positions[-1].header.frame_id=='odom_path_1d'
        subs=node.get_subscriber_names_and_types_by_node('reserve_odometry','/');assert not any('gnss' in n or 'imu' in n for n,_ in subs)
        print(f'CALIBRATED_LAUNCH_PASS selected={selected} params={len(expected)} outputs={len(velocities)} rate={rate:.3f}Hz')
    finally:
        node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGINT)
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
        log.seek(0);print(log.read());log.close()
if __name__=='__main__':main()
