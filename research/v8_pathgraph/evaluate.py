"""Offline external-map position evaluation. All reference use is evaluator-only."""
from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
from pathgraph import Pathgraph, Grid, Settings, Fix, Localizer
spec=importlib.util.spec_from_file_location('pinned_checker_runner',ROOT/'research/v8_checker_20260927/runner.py')
r=importlib.util.module_from_spec(spec);sys.modules[spec.name]=r;spec.loader.exec_module(r)


def configuration():
    return Grid(37,300000.,6100000.,'map',
                'EXPERIMENTAL HYPOTHESIS: GNSS/projected map scale; absent from uploaded map metadata; not reference-fitted',
                confirmed=False,allow_hypothesis=True)


def load_fixes(root):
    db=root/'bags'/r.BAG/(r.BAG+'_0.db3')
    if r.sha(db)!=r.DB_SHA:raise ValueError('DB checksum')
    fixes=[]
    with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as con:
        for receipt,topic,raw in con.execute("SELECT m.timestamp,t.name,m.data FROM messages m JOIN topics t ON m.topic_id=t.id WHERE t.name IN ('/sensing/gnss/master/fix','/sensing/gnss/rover/fix') ORDER BY m.timestamp,m.id"):
            d=r.CDR(raw);sec,ns=d.take('iI',4);frame=r.cdr_string(d)
            status=d.take('b',1);d.take('H',2);lat,lon,alt=d.take('3d',8)
            d.take('9d',8);d.take('B',1)
            if not 0<=len(raw)-d.pos<8 or ns>=1000000000:raise ValueError('Invalid NavSatFix schema')
            fixes.append(Fix(int(sec*1000000000+ns),int(receipt),topic.split('/')[3],lat,lon,int(status),frame))
    return fixes


def replay(routes,grid,settings,origin,arrays,publications,fixes):
    loc=Localizer(routes,grid,settings);rows=[];decisions=[];pending=[];j=0
    for row,publish in zip(arrays,publications):
        ns=origin+round(row[0]*1e9)
        while j<len(fixes) and fixes[j].receipt_ns<=int(publish):pending.append(fixes[j]);j+=1
        due=[f for f in pending if f.stamp_ns<=ns];pending=[f for f in pending if f.stamp_ns>ns]
        if len(pending)>128:raise AssertionError('Future GNSS queue overflow')
        result=loc.advance(int(ns),float(row[2]),int(publish),due);xyz=result['xyz']
        rows.append((row[0],*(xyz if xyz is not None else (np.nan,np.nan,np.nan)),
                     result['s'] if result['s'] is not None else np.nan,
                     result['route_index'] if result['route_index'] is not None else -1))
        decisions.extend(loc.decisions)
    return np.array(rows),dict(loc.counts),decisions


def metrics(checker,reference,predictions,indices,matched,mask):
    good=matched&mask;acc={k:checker.ErrorAccumulator() for k in ('x','y','z','distance')};xy=checker.ErrorAccumulator()
    for i in np.flatnonzero(good):
        ref=reference[int(indices[i])]
        a=r.message(ref['stamp_ns'],0.,ref['xyz'],ref['frame'],ref['child'])
        b=r.message(ref['stamp_ns'],0.,predictions[i,1:4],'map')
        error=checker.position_errors(a,b)
        for k,x in zip(acc,error):acc[k].add(x)
        xy.add(float(np.hypot(error[0],error[1])))
    def one(a):return dict(n=a.count,rmse=a.rmse if a.count else None,maximum=a.maximum_error if a.count else None)
    return {**{k:one(v) for k,v in acc.items()},'xy':one(xy),'matched':int(np.sum(good)),
            'outputs':len(mask),'coverage':float(np.mean(good)),
            'full_bag_xyz_rmse':acc['distance'].rmse if np.all(good) else None}


def intervals(t,mask):
    change=np.flatnonzero(np.diff(np.r_[0,mask.astype(int),0]))
    return [{'start_s':float(t[a]),'end_s':float(t[b-1]),'samples':int(b-a)} for a,b in zip(change[::2],change[1::2])]


def geometry_diagnostic(routes,refs):
    # Evaluator-only ground-truth-to-map projection; never used to estimate route s.
    from scipy.spatial import cKDTree
    xyz=np.array([x['xyz'] for x in refs]);result=[]
    for route in routes:
        p=np.array(route.points);d=p[1:]-p[:-1];h2=np.sum(d[:,:2]**2,axis=1)
        _,near=cKDTree(p[:,:2]).query(xyz[:,:2],k=2)
        candidates=np.clip(np.concatenate((near,near-1),axis=1),0,len(d)-1)
        q=xyz[:,None,:2]-p[candidates,:2];f=np.clip(np.sum(q*d[candidates,:2],axis=2)/h2[candidates],0,1)
        px=p[candidates]+f[:,:,None]*d[candidates];dist=np.linalg.norm(px[:,:,:2]-xyz[:,None,:2],axis=2)
        best=np.argmin(dist,axis=1);ix=np.arange(len(xyz));err=px[ix,best]-xyz;bestxy=dist[ix,best]
        result.append({'route':route.name,'length_m':route.length,'point_count':len(p),
                       'first_reference_distance_xy_m':float(bestxy[0]),'last_reference_distance_xy_m':float(bestxy[-1]),
                       'within_5m_fraction':float(np.mean(bestxy<=5)),
                       'xyz_rms_on_reference_near_map_only_m':float(np.sqrt(np.mean(np.sum(err[bestxy<=5]**2,axis=1)))),
                       'nearest_xy_quantiles_m':dict(zip(('min','median','p90','max'),map(float,np.quantile(bestxy,[0,.5,.9,1])))),
                       'label':'REFERENCE_GEOMETRY_DIAGNOSTIC_NOT_ESTIMATOR','xy':bestxy})
    return result


def run(checker_root,maps,output):
    output.mkdir(parents=True,exist_ok=False);routes=[Pathgraph.load(p) for p in maps];grid=configuration()
    config={mode:Settings(mode=mode) for mode in ('initial_window','first_on_map','sparse')}
    r.save(output/'STARTED.json',{'created':datetime.now(timezone.utc).isoformat(),'candidate_tuning':False,
             'runtime_inputs':['v8 raw distance','allowed rover GNSS fixes','external maps'],
             'reference_input':False,'frame':asdict(grid),'settings':{k:asdict(v) for k,v in config.items()},
             'maps':{str(p.name):r.sha(p) for p in maps},'frozen':r.frozen_sources(),
             'source_sha256':{p.name:r.sha(p) for p in HERE.glob('*.py')},'protocol_sha256':r.sha(HERE/'PROTOCOL.md')})
    data=r.load_data(checker_root);fixes=load_fixes(checker_root);checker=r.load_checker(checker_root)
    refs=sorted(data.references,key=lambda v:v['stamp_ns']);refns=np.array([a['stamp_ns'] for a in refs],np.int64)
    result={'bag':r.BAG,'frame_hypothesis':asdict(grid),'full_route_available':False,'installed_ROS':'NOT_RUN','main_changed':False,
            'profile_changes':False,'results':{},'full_bag_position_admission':False,'GNSS_fix_count':len(fixes)}
    geo=geometry_diagnostic(routes,refs)
    np.savez_compressed(output/'map_coverage.npz',reference_ns=refns,**{f'route_{i}':g.pop('xy') for i,g in enumerate(geo)})
    result['map_geometry_diagnostics']=geo;series={};all_masks=[];indices=matched=None
    for name,model in r.fixed_models().items():
        arrays,pub,diag=r.scheduled_replay(data,model)
        ns=data.origin_ns+np.rint(arrays[:,0]*1e9).astype(np.int64);indices,matched=r.nearest(refns,ns)
        native,info=r.e.g.predict(data.events,model)
        if not np.array_equal(arrays,native,equal_nan=True):raise AssertionError('Native replay drift')
        speed_score=r.e.ex.metrics(arrays[:,0],arrays[:,1],np.array([refs[i]['twist'][0] for i in indices]),matched)
        result['results'][name]={'speed':speed_score,'position':{},'runtime':diag}
        for mode,settings in config.items():
            before=arrays.copy();pred,counts,decisions=replay(routes,grid,settings,data.origin_ns,arrays,pub,fixes)
            if not np.array_equal(before,arrays,equal_nan=True):raise AssertionError('Position changed speed/raw path')
            mask=np.all(np.isfinite(pred[:,1:4]),axis=1);score=metrics(checker,refs,pred,indices,matched,mask)
            score.update(counts=counts,available=intervals(arrays[:,0],mask),missing=intervals(arrays[:,0],~mask),
                         initialized=[x for x in decisions if x['reason']=='initialized'],
                         corrections=[x for x in decisions if x['reason']=='corrected'])
            result['results'][name]['position'][mode]=score;series[(name,mode)]=pred
            if mode!='initial_window':all_masks.append(mask)
            np.savez_compressed(output/(name+'-'+mode+'.npz'),predictions=pred,velocity=arrays[:,1],raw_distance=arrays[:,2],source_ns=ns,receipt_ns=pub,valid=mask)
            r.save(output/(name+'-'+mode+'-decisions.json'),decisions)
            print(name,mode,'coverage',score['coverage'],'XYZ subset RMSE',score['distance']['rmse'],flush=True)
    common=np.logical_and.reduce(all_masks)
    result['common_intersection']={'count':int(common.sum()),'coverage':float(common.mean()),'scores':{}}
    for (name,mode),pred in series.items():
        if mode!='initial_window':result['common_intersection']['scores'][name+'/'+mode]=metrics(checker,refs,pred,indices,matched,common)
    r.frozen_sources();r.save(output/'RESULT.json',result);r.save(output/'MANIFEST.json',{p.name:r.sha(p) for p in output.iterdir() if p.is_file()})
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--checker-root',type=Path,required=True);p.add_argument('--maps',type=Path,nargs=2,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.checker_root,a.maps,a.output)
