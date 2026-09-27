"""Opt-in position adapter around the installed, UNCHANGED v8 observer.

Needs real ROS Humble at execution; offline tests do not certify ROS/DDS.
Run from source with existing installed package, exact v8 YAML and explicit map
paths / grid contract. No canonical entrypoint/config/default is overwritten.
"""
from dataclasses import fields
import json
import math
from pathlib import Path
import time

import rclpy
from sensor_msgs.msg import NavSatFix
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from reserve_odometry.guarded_node import GuardedOdometryNode
from pathgraph import Pathgraph, Grid, Settings, Fix, Localizer


class PositionBridge:
    def __init__(self):
        self.value=None;self.raw_s=None

    def at(self,raw_s):
        value=self.value
        if value is None or value['xyz'] is None or raw_s!=self.raw_s:
            raise ValueError('No authorized map position for this exact output')
        yaw,pitch=value['yaw'],value['pitch']
        sy,cy=math.sin(yaw/2),math.cos(yaw/2);sp,cp=math.sin(pitch/2),math.cos(pitch/2)
        return value['xyz'],(-sy*sp,cy*sp,sy*cp,cy*cp)


class PathgraphNode(GuardedOdometryNode):
    def __init__(self):
        super().__init__()
        if self.route is not None or self.route_s0!=0:
            raise ValueError('Do not combine route_csv/route_s0 with GNSS map adapter')
        paths=self.declare_parameter('map.paths',['']).value
        grid_path=self.declare_parameter('map.grid_config','').value
        if not paths or any(not p for p in paths) or not grid_path:
            raise ValueError('Explicit map.paths and map.grid_config are required')
        grid=Grid(**json.loads(Path(grid_path).read_text()))
        config={f.name:self.declare_parameter('map.'+f.name,getattr(Settings(),f.name)).value for f in fields(Settings)}
        self.localizer=Localizer([Pathgraph.load(p) for p in paths],grid,Settings(**config))
        self.bridge=PositionBridge();self.route=self.bridge;self.route_frame=grid.frame
        self.pending=[];self.map_dropped=0;self.map_reset_counter=self.reset_counter()
        self.map_diag_pub=self.create_publisher(DiagnosticArray,'/result/map_diagnostics',10)
        qos=QoSProfile(depth=128,reliability=ReliabilityPolicy.BEST_EFFORT,history=HistoryPolicy.KEEP_LAST)
        receiver=self.localizer.settings.receiver
        self.create_subscription(NavSatFix,'/sensing/gnss/'+receiver+'/fix',self.gnss,qos)
        self.get_logger().warning('Experimental partial-map layer: missing position before GNSS/on unknown route; CRS confirmed='+str(grid.confirmed))

    def reset_counter(self):
        return self.timeline.resets+self.clock_resets_total

    def gnss(self,msg):
        stamp=msg.header.stamp
        if not 0<=stamp.nanosec<1000000000:
            self.map_dropped+=1;return
        # The receipt clock is monotonic, independent of ROS/bag source timestamps.
        fix=Fix(int(stamp.sec*1000000000+stamp.nanosec),time.perf_counter_ns(),
                self.localizer.settings.receiver,float(msg.latitude),float(msg.longitude),
                int(msg.status.status),msg.header.frame_id)
        self.pending.append(fix)
        if len(self.pending)>128:
            self.pending.pop(0);self.map_dropped+=1

    def clear_position(self):
        self.localizer.reset();self.pending.clear();self.bridge.value=None
        self.map_reset_counter=self.reset_counter()

    def reset_service(self,request,response):
        result=super().reset_service(request,response)
        self.clear_position();return result

    def publish(self,e,held):
        ns=self.origin_ns+round(e.t*1e9)
        if self.map_reset_counter!=self.reset_counter() or (self.localizer.last_ns is not None and ns<=self.localizer.last_ns):
            self.clear_position()
        due=[f for f in self.pending if f.stamp_ns<=ns]
        self.pending=[f for f in self.pending if f.stamp_ns>ns]
        self.bridge.value=self.localizer.advance(int(ns),float(e.s),time.perf_counter_ns(),due)
        self.bridge.raw_s=e.s
        # Parent still publishes the exact original velocity, with original timestamps.
        # PositionBridge.at raises for missing map position, using parent's existing veto.
        super().publish(e,held)

    def diagnostics(self,callback_ms):
        super().diagnostics(callback_ms)
        msg=DiagnosticArray();msg.header.stamp=self.get_clock().now().to_msg()
        status=DiagnosticStatus();status.name='reserve_odometry/map';status.hardware_id='tram'
        current=self.bridge.value or {'status':'UNLOCALIZED'}
        status.message=current['status']
        status.level=DiagnosticStatus.WARN # Partial coverage and CRS confidence are not certified.
        stats={'crs_confirmed':self.localizer.grid.confirmed,'map_queue_dropped':self.map_dropped,
               'route_index':self.localizer.route_index,**dict(self.localizer.counts)}
        status.values=[KeyValue(key=k,value=str(v)) for k,v in stats.items()]
        msg.status=[status];self.map_diag_pub.publish(msg)

def main():
    rclpy.init();node=None
    try:
        node=PathgraphNode();rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:
        if node is not None:node.destroy_node()
        if rclpy.ok():rclpy.shutdown()


if __name__=='__main__':main()
