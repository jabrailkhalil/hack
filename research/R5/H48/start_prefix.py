"""Optional <=3s initial raw-GNSS prefix adapter; no teacher, NumPy or SciPy.

Only an initial antenna-position/edge anchor, NOT a longitudinal estimator,
body heading, certified global localization or future GNSS correction.
"""
from __future__ import annotations
import math
from geometry_interface import Edge,OrderedMetricGraph
from geo_math import LocalENU


def graph_from_map(value,receiver='master'):
    if value.get('kind')!='map' or value.get('schema_version')!=1:raise ValueError('Map schema')
    return OrderedMetricGraph('H48_WGS84_ENU',[
        Edge(e['id'],*e['nodes'],tuple(map(tuple,e['xyz'])),(e['group'],e['bag'],e['receiver']))
        for e in value['edges'] if e['receiver']==receiver])


def initial_anchor(events,start_ns,value):
    """Events MUST arrive in record order. Do not expose finalized H42 fields."""
    graph=graph_from_map(value);frame=LocalENU(value['frame']['origin']['llh'])
    held={};last_record=None;consumed=0;attempts=0;reason='INSUFFICIENT_PREFIX'
    deadline=start_ns+3_000_000_000
    for event in events:
        record=int(event['record_ns'])
        if record>deadline:break  # No payload fields after the closed initial window.
        if last_record is not None and record<last_record:raise ValueError('Arrival order required')
        last_record=record
        if record<start_ns:continue
        consumed+=1;receiver=event['receiver'];kind=event['kind'];stamp=int(event['stamp_ns'])
        if receiver not in ('master','rover') or kind not in ('vel','fix'):continue
        key=(receiver,kind);old=held.get(key)
        if old is not None and stamp<old['stamp_ns']:continue
        field='position' if kind=='fix' else 'linear'
        values=event.get(field)
        valid=isinstance(values,(list,tuple)) and len(values)==3 and all(isinstance(x,(int,float)) and math.isfinite(x) for x in values)
        if kind=='fix':valid=valid and event.get('status',-1)>=0 and abs(values[0])<=90 and abs(values[1])<=180
        if not valid:held.pop(key,None);continue
        if old is not None and stamp==old['stamp_ns']:
            if old[field]!=values:held.pop(key,None)
            continue
        held[key]=event
        m=held.get(('master','vel'));r=held.get(('rover','vel'));f=held.get(('master','fix'))
        if not all(v is not None for v in (m,r,f)):continue
        now=max(m['stamp_ns'],r['stamp_ns'])
        if not all(0<=now-v['stamp_ns']<=250_000_000 for v in (m,r)):reason='STALE_VELOCITY';continue
        if abs(m['stamp_ns']-r['stamp_ns'])>50_000_000:reason='VELOCITY_SKEW';continue
        a=math.hypot(*m['linear'][:2]);b=math.hypot(*r['linear'][:2])
        if abs(a-b)>max(.3,.02*max(a,b)):reason='VELOCITY_DISAGREEMENT';continue
        if f['stamp_ns']>now or abs(f['stamp_ns']-m['stamp_ns'])>200_000_000:reason='STALE_OR_FUTURE_FIX';continue
        attempts+=1
        xyz=frame.forward(f['position'])
        projections=graph.nearest_candidates(xyz,max_distance_m=10.,tie_tolerance_m=.25)
        if not projections:reason='OUT_OF_MAP';continue
        first=projections[0]
        if any(p.edge_id!=first.edge_id or abs(p.s_m-first.s_m)>5 for p in projections):
            reason='AMBIGUOUS_EDGE_OR_ARC';continue
        return dict(status='ANCHORED_ANTENNA_PROXY',edge_id=first.edge_id,s_m=first.s_m,
                    xyz_m=first.xyz_m,record_ns=record,fix_stamp_ns=f['stamp_ns'],
                    elapsed_s=(record-start_ns)*1e-9,distance_m=first.horizontal_distance_m,
                    body_heading=None,consumed_prefix_messages=consumed,projection_attempts=attempts)
    return dict(status='UNLOCALIZED',reason=reason,body_heading=None,consumed_prefix_messages=consumed,projection_attempts=attempts)
