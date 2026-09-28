"""R5-H48: role-locked train map fit/check/full build. Never reads final/test.

Requires verified H42/H43 native locks and the published DESIGN_FREEZE.
Coordinate access uses the unchanged H42 decoder/storage and accepted mask.
No scientific parameters are exposed as CLI options.
"""
from __future__ import annotations
import argparse, csv, datetime, hashlib, importlib, json, math, os
from pathlib import Path
import sys, time
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src/reserve_odometry'))
from geo_math import LocalENU
from map_model import control, robust, tracklets, SegmentIndex, verify_map, save, canonical

FOLDS_SHA='7efb88def952af5089e89c0415256b529bf6e944cda8596387569cc055192356'
TEACHER_MANIFEST='5c8129133758bbb715f2e170122b976f95d0240c18daa731472d910f0bf274d0'


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def read(p):return json.loads(Path(p).read_text())

def source_hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}

def representatives(records):
    seen=set();result=set()
    for r in sorted(records,key=lambda x:x['bag']):
        if r['wire_sha256'] not in seen:result.add(r['bag']);seen.add(r['wire_sha256'])
    return result


def csv_rows(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)


def load_bag(store,teacher,bag,out):
    streams,raw,topics,checks=store.load(bag)
    coords={};counts={};a=np.load(teacher/'arrays'/f'{bag}.npz',allow_pickle=False)
    for receiver in ('master','rover'):
        fix=streams[receiver+'_fix'];ix=a[receiver+'_fix_index'];rows=np.flatnonzero(a['accepted'])
        if np.any((ix[rows]<0)|(ix[rows]>=len(fix['stamp_ns']))):raise AssertionError('Accepted teacher index invalid')
        fi=ix[rows]
        for field in ('stamp_ns','message_id','record_ns'):
            if not np.array_equal(fix[field][fi],a[receiver+'_fix_'+field][rows]):raise AssertionError('Frozen teacher/raw association mismatch')
        # Exact duplicate fix indices can be linked from multiple velocity rows.
        chosen={}
        for row,fidx in zip(rows,fi):chosen.setdefault(int(fidx),int(row))
        bystamp={}
        for fidx,row in chosen.items():bystamp.setdefault(int(fix['stamp_ns'][fidx]),[]).append((fidx,row))
        selected=[];conflicts=0;invalid=0
        for stamp,pairs in sorted(bystamp.items()):
            positions={tuple(fix['position'][i]) for i,_ in pairs}
            if len(positions)!=1:conflicts+=len(pairs);continue
            i,row=min(pairs)
            p=fix['position'][i]
            if fix['status'][i]<0 or not np.all(np.isfinite(p)) or abs(p[0])>90 or abs(p[1])>180:
                invalid+=1;continue
            selected.append((stamp,i,row))
        ids=np.asarray([i for _,i,_ in selected],int);rrows=np.asarray([r for _,_,r in selected],int)
        coords[receiver]=dict(stamp=np.asarray([t for t,_,_ in selected],np.int64),llh=fix['position'][ids],speed=a['speed_mps'][rrows])
        counts[receiver]=dict(accepted_teacher_rows=len(rows),unique_linked_fix_indices=len(chosen),geometry_points=len(ids),
                              conflicting_same_stamp=conflicts,invalid_position_or_height=invalid,frames=sorted(set(map(str,fix['frame_id'][ids]))))
    deadline=store.records[bag]['start_ns']+3_000_000_000
    start=store.records[bag]['start_ns'];prefix=[]
    for _,(topic,typ,record,wire,row) in raw.items():
        if start<=record<=deadline:
            receiver,kind=topic.split('/')[-2:]
            event=dict(receiver=receiver,kind=kind,record_ns=int(record),stamp_ns=int(row['stamp_ns']))
            if kind=='fix':event.update(position=list(row['position']),status=int(row['status']))
            else:event['linear']=list(row['linear'])
            # Prefix may contain invalid fields; preserve nulls and let causal API abstain.
            for field in ('linear','position'):
                if field in event:event[field]=[v if math.isfinite(v) else None for v in event[field]]
            prefix.append(event)
    save(out/'prefix'/f'{bag}.json',dict(start_ns=start,deadline_ns=deadline,events=prefix))
    result=dict(bag=bag,role='train',decoded_gnss_rows=checks,counts=counts,db_sha256=store.records[bag]['sha256'])
    a.close();return coords,result


def phase_load(args,records,out,origin=None):
    sys.path.insert(0,str(args.teacher/'source'))
    storage=importlib.import_module('storage');storage.ROOT=ROOT
    if sha(args.teacher/'R5_HANDOFF.json')!=TEACHER_MANIFEST:raise ValueError('Teacher manifest mismatch')
    (out/'cache').mkdir();(out/'prefix').mkdir()
    store=storage.Store(args.dataset,args.data_root,out/'access.jsonl','train')
    data={};receipts=[]
    for r in sorted(records,key=lambda r:r['bag']):
        bag=r['bag'];d,receipt=load_bag(store,args.teacher,bag,out);receipts.append(receipt)
        if origin is None:
            for rec in ('master','rover'):
                if len(d[rec]['llh']):
                    origin=dict(llh=d[rec]['llh'][0].tolist(),bag=bag,receiver=rec,stamp_ns=int(d[rec]['stamp'][0]));break
        if origin is not None:
            frame=LocalENU(origin['llh'])
            for rec in d:d[rec]['xyz']=np.asarray([frame.forward(p) for p in d[rec]['llh']],float).reshape(-1,3)
        else:
            for rec in d:d[rec]['xyz']=np.empty((0,3))
        storage.savez(out/'cache'/f'{bag}.npz',{rec+'_'+k:v for rec,cols in d.items() for k,v in cols.items()})
        data[bag]=d
        print(bag,{rec:len(d[rec]['stamp']) for rec in d},flush=True)
    save(out/'data_receipts.json',receipts)
    return data,origin


def load_cache(directory,records):
    result={}
    for r in records:
        with np.load(directory/'cache'/f"{r['bag']}.npz",allow_pickle=False) as a:
            result[r['bag']]={rec:{k:a[rec+'_'+k] for k in ('stamp','llh','xyz','speed')} for rec in ('master','rover')}
    return result


def metrics(p):
    d=p['distance'];valid=np.isfinite(d);n=len(d)
    if not n or not np.all(valid):
        return dict(n=n,rmse_m=None,p95_m=None,coverage=None,ambiguous_fraction=None,vertical_rmse_m=None,max_m=None)
    return dict(n=n,rmse_m=float(np.sqrt(np.mean(d*d))),p95_m=float(np.quantile(d,.95)),
                coverage=float(np.mean(d<=10)),ambiguous_fraction=float(np.mean(p['ambiguous'])),
                vertical_rmse_m=float(np.sqrt(np.mean(p['vertical']**2))),max_m=float(d.max()))


def aggregate(rows):
    usable=[r for r in rows if r['rmse_m'] is not None]
    return dict(groups=len(usable),samples=sum(r['n'] for r in usable),
                rmse_m=float(np.mean([r['rmse_m'] for r in usable])) if usable else None,
                p95_m=float(np.mean([r['p95_m'] for r in usable])) if usable else None,
                coverage=float(sum(r['coverage']*r['n'] for r in usable)/sum(r['n'] for r in usable)) if usable else None)


def evaluate(data,metadata,reps,maps,out):
    scores={};bagrows=[];grouprows=[];loo=[];pointwise_loss=0
    indices={name:{r:SegmentIndex(v,r) for r in ('master','rover')} for name,v in maps.items()}
    for bag in sorted(data):
        for rec in ('master','rover'):
            d=data[bag][rec];pred={name:ix[rec].project(d['xyz']) for name,ix in indices.items()}
            if bag in reps:
                b=pred['CONTROL']['distance'];c=pred['ROBUST']['distance'];pointwise_loss+=int(np.sum((b<=10)&~(c<=10)))
            for name,p in pred.items():
                scores[bag,rec,name]=p
                for regime,mask in (('all',np.ones(len(d['speed']),bool)),('moving',d['speed']>=.5),('slow',d['speed']<.5)):
                    bagrows.append(dict(bag=bag,group=metadata[bag]['group'],receiver=rec,model=name,regime=regime,
                                        primary=bag in reps,**metrics({k:v[mask] for k,v in p.items()})))
            arrays={name+'_'+k:v for name,p in pred.items() for k,v in p.items()}
            np.savez_compressed(out/'residuals'/f'{bag}_{rec}.npz',**arrays)
    for group in sorted({r['group'] for r in metadata.values()}):
        for name in maps:
            pieces=[p for (bag,rec,m),p in scores.items() if m==name and bag in reps and metadata[bag]['group']==group]
            joined={k:np.concatenate([p[k] for p in pieces]) if pieces else np.array([]) for k in ('distance','vertical','ambiguous')}
            grouprows.append(dict(group=group,model=name,**metrics(joined)))
    summaries={name:aggregate([r for r in grouprows if r['model']==name]) for name in maps}
    for group in sorted(metadata[bag]['group'] for bag in reps):
        if any(x['excluded_group']==group for x in loo):continue
        vals={name:aggregate([r for r in grouprows if r['model']==name and r['group']!=group]) for name in maps}
        b=vals['CONTROL']['rmse_m'];c=vals['ROBUST']['rmse_m']
        loo.append(dict(excluded_group=group,control_rmse_m=b,robust_rmse_m=c,gain_fraction=1-c/b if b else None))
    for name in maps:
        pieces=[p for (bag,rec,m),p in scores.items() if m==name and bag in reps]
        joined={k:np.concatenate([p[k] for p in pieces]) for k in ('distance','vertical','ambiguous')}
        summaries[name]['pooled']=metrics(joined)
    csv_rows(out/'per_bag_receiver.csv',bagrows);csv_rows(out/'per_group.csv',grouprows);csv_rows(out/'leave_one_group_out.csv',loo)
    save(out/'METRICS.json',dict(models=summaries,pointwise_coverage_loss=pointwise_loss,
                               qualifying_check_groups=sum(r['model']=='CONTROL' and r['n']>=100 and r['rmse_m'] is not None for r in grouprows)))
    return summaries,grouprows,pointwise_loss


def run(args):
    if sha(args.folds)!=FOLDS_SHA:raise ValueError('Canonical fold mismatch')
    folds=read(args.folds);records=folds['records'];meta={r['bag']:r for r in records}
    if len(records)!=64 or len(folds['fitting_groups'])!=20 or len(folds['check_groups'])!=7:raise ValueError('Wrong folds')
    args.output.mkdir(parents=True,exist_ok=False)
    save(args.output/'STARTED.json',dict(stage=args.stage,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        scientific_source=os.environ.get('H48_SOURCE_SHA'),source_hashes=source_hashes(),folds_sha256=sha(args.folds),
        role='train',test_opened=False,method='geometry offline, NOT official XYZ/longitudinal scorer'))
    clock=time.perf_counter();cpu=time.process_time()
    if args.stage=='fit':
        rr=[r for r in records if r['fold']=='fit'];data,origin=phase_load(args,rr,args.output)
        if origin is None:raise RuntimeError('No eligible fitting coordinates')
        save(args.output/'ORIGIN.json',origin)
        tracks,counts=tracklets(data,meta,representatives(rr));save(args.output/'TRACKLET_COUNTS.json',counts)
        c=control(tracks,origin,'FIT_GROUPS_ONLY');r,stats=robust(tracks,c,'FIT_GROUPS_ONLY')
        save(args.output/'CONTROL.json',c);save(args.output/'ROBUST.json',r);save(args.output/'ROBUST_SUPPORT.json',stats)
        checks={k:verify_map(v) for k,v in [('CONTROL',c),('ROBUST',r)]};save(args.output/'MAP_FIT_SEAL.json',dict(maps=checks,source_hashes=source_hashes(),check_coordinates_opened=False))
    elif args.stage=='check':
        seal=read(args.fit/'MAP_FIT_SEAL.json')
        maps={name:read(args.fit/(name+'.json')) for name in ('CONTROL','ROBUST')}
        for name,v in maps.items():
            if hashlib.sha256(canonical(v)).hexdigest()!=seal['maps'][name]['sha256']:raise ValueError('Fit map seal mismatch')
        if seal['source_hashes']!=source_hashes():raise ValueError('Fitting/scoring code changed after fit')
        rr=[r for r in records if r['fold']=='check'];data,origin=phase_load(args,rr,args.output,read(args.fit/'ORIGIN.json'))
        (args.output/'residuals').mkdir()
        summaries,groups,loss=evaluate(data,{r['bag']:r for r in rr},representatives(rr),maps,args.output)
        b=summaries['CONTROL'];c=summaries['ROBUST'];size_ratio=seal['maps']['CONTROL']['bytes']/seal['maps']['ROBUST']['bytes']
        qualified=sum(r['model']=='CONTROL' and r['n']>=100 and r['rmse_m'] is not None for r in groups)
        gain=1-c['rmse_m']/b['rmse_m'] if b['rmse_m'] else None
        p95_change=c['p95_m']/b['p95_m']-1 if b['p95_m'] else None
        reasons=[]
        if not all(v['passed'] for v in seal['maps'].values()):reasons.append('MAP_COMPONENT_CHECK_FAILED')
        if qualified<4:reasons.append('CHECK_GROUP_COVERAGE_INSUFFICIENT')
        if loss:reasons.append('POINTWISE_COVERAGE_LOSS')
        if gain is None or gain<0:reasons.append('RMSE_WORSE_OR_MISSING')
        if gain is None or not (gain>=.05 or (size_ratio>=2 and p95_change is not None and p95_change<=.01)):reasons.append('INSUFFICIENT_GAIN_OR_COMPRESSION')
        selected='ROBUST' if not reasons else ('CONTROL' if seal['maps']['CONTROL']['passed'] and qualified>=4 else None)
        stats=read(args.fit/'ROBUST_SUPPORT.json')
        verdict='CONFIRMED' if not reasons else ('INCONCLUSIVE' if qualified<4 or stats['changed_anchors']==0 else 'REJECTED')
        save(args.output/'SELECTION.json',dict(selected=selected,robust_verdict=verdict,robust_gain_fraction=gain,p95_change_fraction=p95_change,
            compression=size_ratio,pointwise_coverage_loss=loss,reasons=reasons,fit_map_hashes={n:v['sha256'] for n,v in seal['maps'].items()},
            check_summary_hash=sha(args.output/'METRICS.json'),full_train_build_authorized=selected is not None,
            qualification='Control fallback is a proxy component, NOT confirmed improvement'))
    else:
        selection=read(args.check/'SELECTION.json');name=selection['selected']
        if name not in ('CONTROL','ROBUST') or not selection['full_train_build_authorized']:raise ValueError('No selected rule')
        seal=read(args.fit/'MAP_FIT_SEAL.json')
        if seal['source_hashes']!=source_hashes():raise ValueError('Source changed')
        data=load_cache(args.fit,[r for r in records if r['fold']=='fit'])|load_cache(args.check,[r for r in records if r['fold']=='check'])
        origin=read(args.fit/'ORIGIN.json');tracks,counts=tracklets(data,meta,representatives(records))
        c=control(tracks,origin,'ALL_TRAIN_INCLUDING_FORMER_CHECK')
        if name=='ROBUST':v,stats=robust(tracks,c,'ALL_TRAIN_INCLUDING_FORMER_CHECK');save(args.output/'ROBUST_SUPPORT.json',stats)
        else:v=c
        save(args.output/'MAP_V0.json',v);save(args.output/'TRACKLET_COUNTS.json',counts);save(args.output/'VERIFY.json',verify_map(v))
        save(args.output/'BUILD_RECEIPT.json',dict(selection_sha256=sha(args.check/'SELECTION.json'),rule=name,full_train_builds=1,
             reused_evaluation=None,warning='MAP_FIT holdout scores do NOT validate MAP_V0',coordinate_sql_performed=False))
    save(args.output/'ELAPSED.json',dict(wall_s=time.perf_counter()-clock,cpu_s=time.process_time()-cpu,not_ros_latency=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=('fit','check','full'),required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--teacher',type=Path,required=True);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--folds',type=Path,required=True);p.add_argument('--fit',type=Path);p.add_argument('--check',type=Path)
    run(p.parse_args())
