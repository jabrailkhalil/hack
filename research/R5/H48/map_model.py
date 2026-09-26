"""Frozen map construction/scoring; NumPy/SciPy are OFFLINE dependencies only."""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from geometry_interface import Edge, OrderedMetricGraph
from reserve_odometry.route import Route
from geo_math import LocalENU

TOL=0.25
COS15=math.cos(math.radians(15))
MAX_BYTES=1_000_000


def canonical(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def save(path, value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(canonical(value))


def arc(x):return np.r_[0.,np.cumsum(np.linalg.norm(np.diff(x,axis=0),axis=1))]


def interpolate(x, at):
    s=arc(x)
    return np.column_stack([np.interp(at,s,x[:,j]) for j in range(3)])


def tangent(x, at):
    s=arc(x)
    d=interpolate(x,np.minimum(s[-1],at+2.))-interpolate(x,np.maximum(0.,at-2.))
    h=np.linalg.norm(d[:,:2],axis=1)
    return np.divide(d[:,:2],h[:,None],out=np.zeros((len(d),2)),where=h[:,None]>1e-12)


def rdp(x, tolerance=TOL):
    """Iterative, ordered 3D RDP; retains endpoints and closed-loop structure."""
    x=np.asarray(x,float)
    if len(x)<2:return x.copy()
    keep={0,len(x)-1};stack=[(0,len(x)-1)]
    while stack:
        a,b=stack.pop()
        if b-a<2:continue
        d=x[b]-x[a];den=float(d@d);y=x[a+1:b]-x[a]
        u=np.clip(y@d/den,0.,1.) if den>1e-20 else np.zeros(len(y))
        dist=np.linalg.norm(y-u[:,None]*d,axis=1)
        k=int(np.argmax(dist))
        if dist[k]>tolerance:
            k+=a+1;keep.add(k);stack.extend([(a,k),(k,b)])
    return x[sorted(keep)]


def tracklets(data, metadata, representatives):
    tracks=[];counts={'eligible_map_points':0,'discarded_short_tracklets':0,'discarded_short_points':0,'splits':0}
    for bag in sorted(data):
        if bag not in representatives:continue
        for receiver in ('master','rover'):
            d=data[bag][receiver]
            good=d['speed']>=0.5
            x=d['xyz'][good];t=d['stamp'][good]
            counts['eligible_map_points']+=len(x)
            if not len(x):continue
            dt=np.diff(t).astype(float)*1e-9;delta=np.diff(x,axis=0)
            split=np.flatnonzero((dt<=0)|(dt>0.5)|(np.linalg.norm(delta[:,:2],axis=1)>40*dt+2)|(np.abs(delta[:,2])>10*dt+2))+1
            bounds=np.r_[0,split,len(x)];counts['splits']+=len(split)
            for a,b in zip(bounds[:-1],bounds[1:]):
                part=x[a:b];st=t[a:b]
                # Equal XY vertices have no distinct horizontal projection.
                ix=np.r_[True,np.linalg.norm(np.diff(part[:,:2],axis=0),axis=1)>1e-6]
                part=part[ix];st=st[ix]
                if len(part)<3 or arc(part)[-1]<5:
                    counts['discarded_short_tracklets']+=1;counts['discarded_short_points']+=len(part);continue
                tracks.append(dict(id=f'e{len(tracks):04d}',receiver=receiver,group=metadata[bag]['group'],bag=bag,
                                   stamp_bounds=[int(st[0]),int(st[-1])],xyz=part))
    return tracks,counts


def map_value(tracks, origin, representation, scope):
    edges=[]
    for tr in tracks:
        x=np.round(tr['xyz'],6)
        if len(x)>1:x=x[np.r_[True,np.linalg.norm(np.diff(x[:,:2],axis=0),axis=1)>1e-6]]
        edges.append({k:tr[k] for k in ('id','receiver','group','bag','stamp_bounds')}|
                     dict(nodes=[tr['id']+':a',tr['id']+':b'],xyz=x.tolist()))
    return dict(schema_version=1,kind='map',representation=representation,scope=scope,
                qualification='ANTENNA_TRAJECTORY_PROXY_ONLY',frame=dict(name='H48_WGS84_ENU',origin=origin,
                units='m',height='NavSatFix WGS84 ellipsoid, not geoid',official_mgrs_transform=None,
                antenna_to_base_link=None),topology='observed ordered tracklets; proximity/crossing NEVER connects edges',
                baseline='b2783206000091ab11a1c11ac3ff79082188a4fb',edges=edges)


def control(tracks,origin,scope):
    return map_value([t|{'xyz':rdp(t['xyz'])} for t in tracks],origin,'CONTROL',scope)


def robust(tracks,control_map,scope):
    """Exactly one group-balanced, bounded transverse median/smoothing pass."""
    indices={};stats=dict(anchors=0,supported_anchors=0,changed_anchors=0,ambiguous_group_matches=0,max_shift_m=0.,edges=[])
    for receiver in ('master','rover'):
        subset=[t for t in tracks if t['receiver']==receiver]
        if not subset:continue
        x=np.concatenate([t['xyz'] for t in subset]);tan=np.concatenate([tangent(t['xyz'],arc(t['xyz'])) for t in subset])
        groups=np.concatenate([np.full(len(t['xyz']),t['group']) for t in subset])
        indices[receiver]=(cKDTree(x[:,:2]),x,tan,groups)
    result=[]
    for edge in control_map['edges']:
        x=np.asarray(edge['xyz']);s=arc(x);at=np.unique(np.r_[s,np.arange(0.,s[-1],2.)])
        a=interpolate(x,at);tan=tangent(x,at);normal=np.column_stack([-tan[:,1],tan[:,0]])
        shifts=np.zeros(len(a));supported=np.zeros(len(a),bool);support_counts=np.ones(len(a),int)
        tree,p,pt,pg=indices[edge['receiver']]
        for i,neighbours in enumerate(tree.query_ball_point(a[:,:2],r=2.)):
            ix=np.asarray(neighbours,int)
            if not len(ix) or not np.linalg.norm(tan[i]):continue
            ix=ix[(pg[ix]!=edge['group'])&(np.abs(pt[ix]@tan[i])>=COS15)]
            votes=[0.]
            for group in np.unique(pg[ix]):
                gi=ix[pg[ix]==group];d=np.linalg.norm(p[gi,:2]-a[i,:2],axis=1)
                # Stable source-index tie breaker, not neighbour traversal order.
                k=np.lexsort((gi,d))[0];near=gi[d<=d[k]+.25]
                offsets=(p[near,:2]-a[i,:2])@normal[i]
                vote=float((p[gi[k],:2]-a[i,:2])@normal[i])
                if np.any(np.abs(offsets-vote)>.5):stats['ambiguous_group_matches']+=1;continue
                votes.append(vote)
            support_counts[i]=len(votes)
            if len(votes)>=3:supported[i]=True;shifts[i]=np.clip(np.median(votes),-.5,.5)
        smoothed=np.zeros(len(a))
        for i in np.flatnonzero(supported):
            lo=np.searchsorted(at,at[i]-5);hi=np.searchsorted(at,at[i]+5,side='right')
            weights=np.maximum(0.,1.-np.abs(at[lo:hi]-at[i])/5.)
            smoothed[i]=float(weights@shifts[lo:hi]/weights.sum())
        smoothed[[0,-1]]=0.;a[:,:2]+=smoothed[:,None]*normal
        stats['anchors']+=len(a);stats['supported_anchors']+=int(supported.sum());stats['changed_anchors']+=int(np.sum(np.abs(smoothed)>1e-6))
        stats['max_shift_m']=max(stats['max_shift_m'],float(np.max(np.abs(smoothed))))
        stats['edges'].append(dict(id=edge['id'],anchors=len(a),supported=int(supported.sum()),support_group_max=int(support_counts.max())))
        result.append({k:edge[k] for k in ('id','receiver','group','bag','stamp_bounds')}|{'xyz':rdp(a)})
    return map_value(result,control_map['frame']['origin'],'ROBUST',scope),stats


class SegmentIndex:
    """Exact XY projection, with conservative midpoint ball pruning (not nearest-vertex error)."""
    def __init__(self, value, receiver):
        starts=[];ends=[];ids=[];arc0=[];lengths=[]
        for j,e in enumerate(value['edges']):
            if e['receiver']!=receiver:continue
            x=np.asarray(e['xyz']);s=arc(x)
            starts.extend(x[:-1]);ends.extend(x[1:]);ids.extend([j]*(len(x)-1));arc0.extend(s[:-1]);lengths.extend(np.diff(s))
        self.a=np.asarray(starts).reshape(-1,3);self.b=np.asarray(ends).reshape(-1,3);self.ids=np.asarray(ids);self.s=np.asarray(arc0);self.length=np.asarray(lengths)
        self.d=self.b-self.a;self.den=np.sum(self.d[:,:2]**2,axis=1)
        self.mid=(self.a[:,:2]+self.b[:,:2])*.5
        self.tree=cKDTree(self.mid) if len(starts) else None
        self.half=float(np.sqrt(self.den).max()/2) if len(starts) else 0
        if len(starts) and np.any(self.den<=1e-12):raise ValueError('Degenerate XY segment')

    def project(self, queries):
        q=np.asarray(queries,float);n=len(q)
        dist=np.full(n,np.nan);dz=dist.copy();eid=np.full(n,-1,int);ss=dist.copy();amb=np.zeros(n,bool)
        if self.tree is None:return dict(distance=dist,vertical=dz,edge=eid,s=ss,ambiguous=amb)
        _,near=self.tree.query(q[:,:2]);d0=q-self.a[near];u=np.clip(np.sum(d0[:,:2]*self.d[near,:2],axis=1)/self.den[near],0,1)
        bound=np.linalg.norm(d0[:,:2]-u[:,None]*self.d[near,:2],axis=1)
        for lo in range(0,n,256):
            hi=min(n,lo+256)
            balls=self.tree.query_ball_point(q[lo:hi,:2],bound[lo:hi]+self.half+.25000001)
            for row,possible in enumerate(balls,lo):
                ix=np.asarray(possible,int);v=q[row]-self.a[ix]
                t=np.clip(np.sum(v[:,:2]*self.d[ix,:2],axis=1)/self.den[ix],0.,1.)
                d=np.linalg.norm(v[:,:2]-t[:,None]*self.d[ix,:2],axis=1)
                k=np.lexsort((ix,d))[0];si=self.s[ix]+t*self.length[ix];best=ix[k]
                dist[row]=d[k];dz[row]=q[row,2]-(self.a[best,2]+t[k]*self.d[best,2]);eid[row]=self.ids[best];ss[row]=si[k]
                amb[row]=bool(np.any((d<=d[k]+.25)&((self.ids[ix]!=eid[row])|(np.abs(si-si[k])>5))))
        return dict(distance=dist,vertical=dz,edge=eid,s=ss,ambiguous=amb)


def as_graph(value,receiver=None):
    edges=[Edge(e['id'],*e['nodes'],tuple(map(tuple,e['xyz'])),(e['group'],e['bag'],e['receiver'])) for e in value['edges'] if receiver is None or e['receiver']==receiver]
    return OrderedMetricGraph('H48_WGS84_ENU',edges)


def verify_map(value):
    errors=[];n=sum(len(e['xyz']) for e in value['edges']);raw=canonical(value)
    if len(raw)>MAX_BYTES:errors.append('UNCOMPRESSED_BUDGET_EXCEEDED')
    if n>20000:errors.append('POINT_BUDGET_EXCEEDED')
    if not 1<=len(value['edges'])<=1024:errors.append('EDGE_BUDGET_EXCEEDED_OR_EMPTY')
    roundtrip=0.;reverse=0.;arc_count=0
    try:
        graph=as_graph(value);frame=LocalENU(value['frame']['origin']['llh'])
        for edge in value['edges']:
            r=Route(edge['xyz']);rev=Route(edge['xyz'][::-1]);arc_count+=len(r.arc)
            for s in np.linspace(0.,r.arc[-1],9):
                a,_=r.at(float(s));b,_=rev.at(float(np.clip(rev.arc[-1]-s,0,rev.arc[-1])))
                reverse=max(reverse,math.dist(a,b));llh=frame.reverse(a);back=frame.forward(llh)
                roundtrip=max(roundtrip,math.dist(a,back))
            if graph.successors(edge['id']):raise AssertionError('Inferred unintended connectivity')
        if reverse>1e-6:errors.append('REVERSE_CONTINUITY')
        if roundtrip>1e-5:errors.append('GEODETIC_ROUNDTRIP')
    except (ValueError,AssertionError) as e:errors.append(str(e))
    return dict(passed=not errors,errors=errors,edges=len(value['edges']),points=n,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
                reverse_max_m=reverse,geodetic_roundtrip_max_m=roundtrip,arc_vertices_checked=arc_count,
                topology='disconnected observed chains; crossing does not create connections; physical switches unresolved')
