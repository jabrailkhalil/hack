"""Explicit external Pathgraph + causal GNSS position; never modifies v8 speed.

No reference-topic input, invented connecting edges, extrapolation, route switch,
or hard-coded bag start. Unknown/off-route position is absent, not (0,0,0).
"""
from bisect import bisect_right, bisect_left
from collections import deque, Counter
from dataclasses import dataclass
import csv
import hashlib
import json
import math
from pathlib import Path

ARMS = {'master': (-9.873, 0., 3.), 'rover': (2.563, 0., 3.)}


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def angle(x):
    return math.atan2(math.sin(x), math.cos(x))


@dataclass(frozen=True)
class Grid:
    """Explicit horizontal WGS84/UTM + translation; NOT inferred from reference.

    Supplied maps do not declare a CRS. A hypothesis needs explicit opt-in.
    GNSS altitude is not transformed or used in XY map matching / map Z output.
    """
    zone: int
    easting_origin_m: float
    northing_origin_m: float
    frame: str
    provenance: str
    confirmed: bool = False
    allow_hypothesis: bool = False

    def __post_init__(self):
        if type(self.zone) is not int or not 1 <= self.zone <= 60:
            raise ValueError('UTM zone must be 1..60')
        if not all(number(x) for x in (self.easting_origin_m, self.northing_origin_m)):
            raise ValueError('Finite explicitly declared origins required')
        if not isinstance(self.frame, str) or not self.frame.strip() or not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError('Frame and CRS provenance required')
        if type(self.confirmed) is not bool or type(self.allow_hypothesis) is not bool:
            raise ValueError('Confirmation flags must be booleans')
        if not self.confirmed and not self.allow_hypothesis:
            raise ValueError('CRS unconfirmed; explicit experimental opt-in required')

    def xy(self, latitude, longitude):
        # Sixth-order WGS84 transverse-Mercator series, restricted to a UTM zone.
        # Verified against PROJ on the test-region grid; not a universal geodesy library.
        center = 6*self.zone-183
        if not number(latitude) or not number(longitude) or not 0 <= latitude <= 84 or abs(longitude-center) > 3:
            raise ValueError('Northern UTM coordinates outside selected zone')
        phi, dl = math.radians(latitude), math.radians(longitude-center)
        a, f = 6378137., 1/298.257223563
        e2 = f*(2-f); ep = e2/(1-e2)
        sn, cs, tn = math.sin(phi), math.cos(phi), math.tan(phi)
        n = a/math.sqrt(1-e2*sn*sn); t=tn*tn; c=ep*cs*cs; u=cs*dl
        meridian=a*((1-e2/4-3*e2**2/64-5*e2**3/256)*phi
                    -(3*e2/8+3*e2**2/32+45*e2**3/1024)*math.sin(2*phi)
                    +(15*e2**2/256+45*e2**3/1024)*math.sin(4*phi)
                    -35*e2**3/3072*math.sin(6*phi))
        x=500000+.9996*n*(u+(1-t+c)*u**3/6+(5-18*t+t*t+72*c-58*ep)*u**5/120)
        y=.9996*(meridian+n*tn*(u*u/2+(5-t+9*c+4*c*c)*u**4/24+(61-58*t+t*t+600*c-330*ep)*u**6/720))
        return x-self.easting_origin_m, y-self.northing_origin_m


class Pathgraph:
    def __init__(self, document, path_index=0, name='route'):
        if not isinstance(document, dict) or not isinstance(document.get('points'), list) or not isinstance(document.get('paths'), list):
            raise ValueError('Expected points and paths arrays')
        if type(path_index) is not int or not 0 <= path_index < len(document['paths']):
            raise ValueError('Invalid path index')
        rows=document['points']; indices=document['paths'][path_index].get('point_indices')
        if not isinstance(indices,list) or not 2 <= len(indices) <= 20000:
            raise ValueError('Need 2..20000 ordered point indices')
        if any(type(i) is not int or i < 0 or i >= len(rows) for i in indices):
            raise ValueError('Invalid point index')
        self.points=[]; self.tang=[]; self.curv=[]
        for i in indices:
            row=rows[i]
            if not isinstance(row,dict) or any(not number(row.get(k)) for k in ('x','y','z','tang','curv')):
                raise ValueError('Nonfinite / missing path point field')
            self.points.append(tuple(float(row[k]) for k in ('x','y','z')))
            self.tang.append(float(row['tang'])); self.curv.append(float(row['curv']))
        self.indices=tuple(indices);self.name=name;self.arc=[0.];self.segments=[]
        for a,b in zip(self.points,self.points[1:]):
            dx,dy,dz=(y-x for x,y in zip(a,b));h=math.hypot(dx,dy);length=math.sqrt(h*h+dz*dz)
            if h <= 1e-6 or length > 100:
                raise ValueError('Zero-length/vertical segment or unsupported >100m connection')
            yaw=math.atan2(dy,dx);pitch=-math.atan2(dz,h)
            self.segments.append((dx,dy,dz,h,length,yaw,pitch));self.arc.append(self.arc[-1]+length)
        self.length=self.arc[-1]
        self.source_sha256=None

    @classmethod
    def load(cls,path,path_index=0):
        path=Path(path)
        if path.stat().st_size > 16*1024*1024:raise ValueError('Map size budget exceeded')
        raw=path.read_bytes();obj=cls(json.loads(raw),path_index,path.stem)
        obj.source_sha256=hashlib.sha256(raw).hexdigest();return obj

    def at(self,s):
        if not number(s) or not 0 <= s <= self.length:raise ValueError('Outside authorized route')
        i=max(0,min(len(self.segments)-1,bisect_right(self.arc,s)-1));seg=self.segments[i]
        fraction=(s-self.arc[i])/seg[4]
        xyz=tuple(self.points[i][k]+fraction*seg[k] for k in range(3))
        # Stored tangent interpolation wraps angles, never jumps through zero at +/-pi.
        yaw=self.tang[i]+fraction*angle(self.tang[i+1]-self.tang[i])
        return xyz,angle(yaw),seg[6]

    def project(self, xy, arm, expected_s=None, heading=None, max_innovation=40., cross_gate=8.):
        if len(xy)!=2 or not all(number(x) for x in xy):raise ValueError('Invalid XY')
        if len(arm)!=3 or not all(number(x) for x in arm):raise ValueError('Invalid lever arm')
        if (expected_s is not None and not number(expected_s)) or (heading is not None and not number(heading)):
            raise ValueError('Nonfinite expected position / heading')
        xarm,yarm,zarm=arm; candidates=[]
        if expected_s is None: lo,hi=0,len(self.segments)
        else:
            lo=max(0,bisect_right(self.arc,expected_s-max_innovation)-2)
            hi=min(len(self.segments),bisect_right(self.arc,expected_s+max_innovation)+1)
        for i in range(lo,hi):
            dx,dy,dz,h,length,yaw,pitch=self.segments[i]
            if heading is not None and abs(angle(yaw-heading)) > math.pi/3:continue
            cy,sy,cp,sp=math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
            # Rz(yaw) Ry(pitch) applied to body-frame antenna lever arm.
            ox=cy*(cp*xarm+sp*zarm)-sy*yarm;oy=sy*(cp*xarm+sp*zarm)+cy*yarm
            a=self.points[i];qx=xy[0]-ox-a[0];qy=xy[1]-oy-a[1]
            f=max(0.,min(1.,(qx*dx+qy*dy)/(h*h)));s=self.arc[i]+f*length
            if expected_s is not None and abs(s-expected_s) > max_innovation:continue
            residual=math.hypot(qx-f*dx,qy-f*dy)
            candidates.append((residual,s,i))
        if not candidates:return None,'heading_or_innovation_gate'
        best=min(candidates)
        if best[0] > cross_gate:return None,'off_map'
        if any(abs(s-best[1])>8. and residual <= best[0]+.5 for residual,s,_ in candidates):
            return None,'ambiguous_projection'
        return {'s':best[1],'residual_xy_m':best[0],'segment':best[2]},None

    def write_csv(self,path):
        # Exact float round-trip, original path order, no simplification.
        with Path(path).open('x',newline='',encoding='utf-8') as out:
            writer=csv.writer(out);writer.writerow(('x','y','z'))
            writer.writerows(self.points)


@dataclass(frozen=True)
class Fix:
    stamp_ns: int
    receipt_ns: int
    receiver: str
    latitude: float
    longitude: float
    status: int = 0
    frame_id: str = 'gps'


@dataclass(frozen=True)
class Settings:
    mode: str = 'sparse' # initial_window | first_on_map | sparse
    receiver: str = 'rover'
    initial_window_s: float = 5.
    max_age_s: float = 2.
    interval_s: float = 30.
    cross_gate_m: float = 8.
    innovation_gate_m: float = 40.
    gain: float = .25
    max_correction_m: float = 1.
    course_distance_m: float = 2.
    course_window_s: float = 2.

    def __post_init__(self):
        if not isinstance(self.mode,str) or not isinstance(self.receiver,str) or self.mode not in ('initial_window','first_on_map','sparse') or self.receiver not in ARMS:raise ValueError('Unknown mode or receiver')
        for key in ('initial_window_s','max_age_s','interval_s','cross_gate_m','innovation_gate_m','max_correction_m','course_distance_m','course_window_s'):
            value=getattr(self,key)
            if not number(value) or not 0 < value <= 3600:raise ValueError('Invalid '+key)
        if self.max_age_s>5 or self.course_window_s>5 or not number(self.gain) or not 0<=self.gain<=1:
            raise ValueError('Invalid age/history/gain')


class Localizer:
    def __init__(self,routes,grid,settings=Settings()):
        if not 1 <= len(routes) <= 8:raise ValueError('Need 1..8 external routes')
        self.routes=tuple(routes);self.grid=grid;self.settings=settings;self.reset()

    def reset(self):
        self.history=deque(maxlen=256);self.fix_history=deque(maxlen=64)
        self.origin_ns=self.last_ns=self.last_stamp_ns=self.last_slot_ns=None
        self.route_index=self.offset=self.source_frame=None;self.counts=Counter();self.decisions=[]
        self.exhausted=False

    def raw_at(self,stamp):
        history=list(self.history);i=bisect_left([a for a,b in history],stamp)
        if i<len(history) and history[i][0]==stamp:return history[i][1]
        if i==0 or i==len(history):return None
        a,x=history[i-1];b,y=history[i]
        if (b-a)>150000000:return None
        return x+(y-x)*(stamp-a)/(b-a)

    def record(self,reason,fix,**extra):
        self.counts[reason]+=1
        # Bounded per-step decisions; counters aggregate the full run.
        if len(self.decisions)<256:
            self.decisions.append(dict(reason=reason,stamp_ns=fix.stamp_ns,applied_ns=self.last_ns,**extra))

    def observe(self,fix,receipt_now_ns):
        c=self.settings
        if fix.receiver!=c.receiver:return
        if type(fix.stamp_ns) is not int or type(fix.receipt_ns) is not int:return self.record('invalid_time',fix)
        if fix.stamp_ns>self.last_ns or fix.receipt_ns>receipt_now_ns:return self.record('future',fix)
        if (self.last_ns-fix.stamp_ns)/1e9 > c.max_age_s:return self.record('stale',fix)
        if self.last_stamp_ns is not None and fix.stamp_ns<=self.last_stamp_ns:return self.record('duplicate_or_reordered',fix)
        self.last_stamp_ns=fix.stamp_ns
        if type(fix.status) is not int or fix.status not in (0,1,2):return self.record('bad_status',fix)
        if not isinstance(fix.frame_id,str) or not fix.frame_id or (self.source_frame is not None and fix.frame_id!=self.source_frame):return self.record('frame_change',fix)
        try:xy=self.grid.xy(fix.latitude,fix.longitude)
        except ValueError:return self.record('bad_coordinate',fix)
        if self.source_frame is None:self.source_frame=fix.frame_id
        while self.fix_history and fix.stamp_ns-self.fix_history[0][0]>int(c.course_window_s*1e9):self.fix_history.popleft()
        heading=None
        if self.fix_history:
            old_t,old_xy=self.fix_history[0]
            dx,dy=xy[0]-old_xy[0],xy[1]-old_xy[1]
            if fix.stamp_ns-old_t>=300000000 and math.hypot(dx,dy)>=c.course_distance_m:
                heading=math.atan2(dy,dx)
        self.fix_history.append((fix.stamp_ns,xy))
        if c.mode=='initial_window' and fix.stamp_ns-self.origin_ns>int(c.initial_window_s*1e9):return self.record('initial_window_closed',fix)
        if self.route_index is not None and c.mode!='sparse':return self.record('initial_only',fix)
        if self.exhausted:return self.record('route_exhausted',fix)
        raw=self.raw_at(fix.stamp_ns)
        if raw is None:return self.record('no_history',fix)
        if self.route_index is None:
            if heading is None:return self.record('no_course',fix)
            proposed=[]
            for i,route in enumerate(self.routes):
                p,reason=route.project(xy,ARMS[c.receiver],heading=heading,cross_gate=c.cross_gate_m)
                if p is not None:proposed.append((p['residual_xy_m'],i,p))
            if not proposed:return self.record('off_map_or_heading',fix)
            proposed.sort(key=lambda p:p[:2])
            if len(proposed)>1 and proposed[1][0]-proposed[0][0]<.5:return self.record('ambiguous_route',fix)
            _,i,p=proposed[0]
            self.route_index=i;self.offset=p['s']-raw;self.last_slot_ns=fix.stamp_ns
            return self.record('initialized',fix,route_index=i,route_s=p['s'],residual_xy_m=p['residual_xy_m'])
        if fix.stamp_ns-self.last_slot_ns < int(c.interval_s*1e9):return self.record('thinned',fix)
        self.last_slot_ns=fix.stamp_ns # Also consume rejected slots; never select a convenient residual in a burst.
        expected=raw+self.offset
        p,reason=self.routes[self.route_index].project(xy,ARMS[c.receiver],expected_s=expected,
                    max_innovation=c.innovation_gate_m,cross_gate=c.cross_gate_m)
        if p is None:return self.record(reason,fix)
        innovation=p['s']-expected
        correction=max(-c.max_correction_m,min(c.max_correction_m,c.gain*innovation))
        self.offset+=correction
        self.record('corrected',fix,innovation_m=innovation,correction_m=correction,residual_xy_m=p['residual_xy_m'])

    def advance(self,time_ns,raw_s,receipt_now_ns,fixes=()):
        if type(time_ns) is not int or type(receipt_now_ns) is not int or not number(raw_s):raise ValueError('Invalid clock or distance')
        if self.last_ns is not None and time_ns<=self.last_ns:raise ValueError('Clock reversal; explicit reset required')
        if self.origin_ns is None:self.origin_ns=time_ns
        self.last_ns=time_ns;self.history.append((time_ns,raw_s));self.decisions=[]
        for fix in fixes:self.observe(fix,receipt_now_ns)
        if self.route_index is None:return {'status':'UNLOCALIZED','xyz':None,'route_index':None,'s':None,'yaw':None,'pitch':None}
        route=self.routes[self.route_index];s=raw_s+self.offset
        if self.exhausted or not 0<=s<=route.length:
            self.exhausted=True
            return {'status':'OUTSIDE_MAP','xyz':None,'route_index':self.route_index,'s':s,'yaw':None,'pitch':None}
        xyz,yaw,pitch=route.at(s)
        return {'status':'MAP_LOCALIZED','xyz':xyz,'route_index':self.route_index,'s':s,'yaw':yaw,'pitch':pitch}
