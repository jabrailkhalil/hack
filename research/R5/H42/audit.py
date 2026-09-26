"""Versioned H42 train audit then descriptive development; no fitting/evaluator."""
import argparse, collections, datetime, hashlib, json, math, os, platform, sys
from pathlib import Path
import numpy as np
from policy import POLICY, REASONS, FLAGS, make_teacher, unique
from storage import Store, ROOT, SPLIT_SHA, DATA_SHA, BASE, sha, save_json, savez
CODE=Path(__file__).resolve().parent

def hashes():
    paths=list(CODE.glob('*.py'))+list((CODE/'contracts').glob('*.json'))
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)}

def quantiles(a):
    a=np.asarray(a,float);a=a[np.isfinite(a)]
    return dict(zip(('min','p50','p95','max'),map(float,np.quantile(a,[0,.5,.95,1])))) if len(a) else None

def stream_stats(a,kind):
    t=a['stamp_ns'];u,ix,n,c=unique(a)
    stats=dict(messages=len(t),unique_stamps=len(u),duplicate_rows=int(len(t)-len(u)),
               conflicting_stamps=int(c.sum()),frame_ids=dict(collections.Counter(map(str,a['frame_id']))),
               nonmonotonic_source_steps=int(np.sum(np.diff(t)<0)),
               source_gap_over_500ms=int(np.sum(np.diff(u)>500_000_000)),
               source_gap_s=quantiles(np.diff(u)/1e9),record_minus_source_s=quantiles((a['record_ns']-t)/1e9))
    if kind=='fix':
        stats.update(status=dict(collections.Counter(map(str,a['status']))),
          covariance_type=dict(collections.Counter(map(str,a['covariance_type']))),
          zero_covariance=int(np.sum(np.all(a['covariance']==0,axis=1))),
          nonfinite_latlon=int(np.sum(~np.all(np.isfinite(a['position'][:,:2]),axis=1))),
          altitude_unknown=int(np.sum(~np.isfinite(a['position'][:,2]))))
    else:stats.update(zero_speed=int(np.sum(np.hypot(a['linear'][:,0],a['linear'][:,1])==0)),
                      nonfinite_linear=int(np.sum(~np.all(np.isfinite(a['linear']),axis=1))))
    return stats

def simple_displacement(fix,a,b):
    if min(a,b)<0:return None
    x,y=fix['position'][[a,b],:2]
    if not np.all(np.isfinite([x,y])):return None
    p,q=np.radians([x,y]);dl=q-p
    v=math.sin(dl[0]/2)**2+math.cos(p[0])*math.cos(q[0])*math.sin(dl[1]/2)**2
    return 6371000.*2*math.asin(math.sqrt(min(1,max(0,v))))

def zero_episodes(t,raw):
    good=(t['flag_bits']&FLAGS['BOTH_ZERO'])!=0;episodes=[];start=None
    for i in range(len(good)+1):
        hit=i<len(good) and good[i]
        gap=i>0 and i<len(good) and t['stamp_ns'][i]-t['stamp_ns'][i-1]>500_000_000
        if start is not None and (not hit or gap):
            end=i-1;duration=(int(t['stamp_ns'][end])-int(t['stamp_ns'][start]))/1e9
            if duration>=1:
                episodes.append(dict(start_ns=int(t['stamp_ns'][start]),end_ns=int(t['stamp_ns'][end]),
                  duration_s=duration,rows=end-start+1,accepted_rows=int(t['accepted'][start:end+1].sum()),
                  master_horizontal_endpoint_displacement_m=simple_displacement(raw['master_fix'],int(t['master_fix_index'][start]),int(t['master_fix_index'][end])),
                  rover_horizontal_endpoint_displacement_m=simple_displacement(raw['rover_fix'],int(t['rover_fix_index'][start]),int(t['rover_fix_index'][end])),
                  qualification='Recorded both-zero stationary proxy, not independently verified stop'))
            start=None
        if hit and start is None:start=i
    return episodes

def examples(bag,teacher,raw,by_id,out):
    """One deterministic real witness per observed code per bag, with neighbouring CDR."""
    records=[]
    categories=[('reason',name,teacher['reason_bits']&bit!=0) for name,bit in REASONS.items()]
    categories += [('flag',name,teacher['flag_bits']&bit!=0) for name,bit in FLAGS.items()]
    categories += [('state','AGREED',teacher['accepted'])]
    for kind,name,mask in categories:
        hit=np.flatnonzero(mask)
        if not len(hit):continue
        i=int(hit[0]); witnesses=[]
        for rec in ('master','rover'):
            vi=int(teacher[rec+'_index'][i]);fi=int(teacher[rec+'_fix_index'][i])
            for key,index in [(rec+'_vel',v) for v in (vi-1,vi,vi+1) if vi>=0]+[(rec+'_fix',fi)]:
                arr=raw[key]
                if not 0<=index<len(arr['message_id']):continue
                mid=int(arr['message_id'][index]);topic,typ,record,bytes_,row=by_id[mid]
                rel=f'examples/cdr/{bag}-{mid}.cdr';p=out/rel;p.parent.mkdir(parents=True,exist_ok=True)
                if not p.exists():p.write_bytes(bytes_)
                witnesses.append(dict(path=rel,sha256=hashlib.sha256(bytes_).hexdigest(),message_id=mid,
                   topic=topic,type=typ,record_ns=record,source_ns=int(row['stamp_ns']),frame_id=row['frame_id']))
        records.append(dict(bag=bag,category=kind,code=name,teacher_row=i,source_ns=int(teacher['stamp_ns'][i]),
             accepted=bool(teacher['accepted'][i]),reason_bits=int(teacher['reason_bits'][i]),
             flag_bits=int(teacher['flag_bits'][i]),witnesses=witnesses))
    return records

def frozen(path):
    f=json.loads(Path(path).read_text())
    if f['kind']!='teacher_policy' or f['hashes']!=hashes():raise ValueError('Frozen teacher source/policy/folds mismatch')
    if not f.get('published_commit'):raise PermissionError('External policy freeze publication not recorded')
    return f

def run(args):
    freeze=frozen(args.freeze) if args.role=='development' else None
    if args.role=='development' and freeze is None:raise PermissionError('Freeze required')
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    for folder in ('bags','arrays','examples'): (out/folder).mkdir()
    if json.loads((CODE/'contracts/TEACHER_POLICY.json').read_text())!=POLICY:raise AssertionError('Policy constants/JSON differ')
    folds=json.loads((CODE/'contracts/TRAIN_FOLDS.json').read_text());gmap={x['group']:x for x in folds['groups']}
    store=Store(args.dataset,args.data_root,out/'ACCESS.jsonl',args.role,freeze)
    selected=sorted(r['bag'] for r in store.records.values() if r['split']==args.role)
    save_json(out/'STARTED.json',dict(baseline=BASE,role=args.role,dataset_sha256=DATA_SHA,
      code_hashes=hashes(),source_commit=args.source_commit,plan_commit='d981d3ebcf28abd2dda9b06d5b659d7b3e5bd762',
      python=platform.python_version(),numpy=np.__version__,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
      execution='local_container',official_reference_used=False,vehicle_payload_read=False,
      validation_opened=False,test_opened=False,freeze=freeze))
    bags=[];witnesses=[]
    for bag in selected:
        r=store.records[bag];raw,by_id,topics,checks=store.load(bag)
        t=make_teacher(raw['master_vel'],raw['rover_vel'],raw['master_fix'],raw['rover_fix'])
        # Offline matching and duplicate arbitration require finalization of the entire GNSS bag.
        maxrecord=max((int(x['record_ns'].max()) for x in raw.values() if len(x['record_ns'])),default=-1)
        t['available_after_bag_record_ns']=np.full(len(t['stamp_ns']),maxrecord,np.int64)
        arrays={key+'__'+name:a for key,stream in raw.items() for name,a in stream.items()}
        arrays.update({'teacher__'+name:a for name,a in t.items()})
        filename=out/'arrays'/(bag+'.npz');savez(filename,arrays)
        n=len(t['accepted']);paired=(t['master_index']>=0)&(t['rover_index']>=0)
        st={name:stream_stats(a,name.split('_')[-1]) for name,a in raw.items()}
        item=dict(bag=bag,group=r['group'],label=r['vehicle'],role=args.role,
          fold=gmap[r['group']]['fold'] if args.role=='train' else 'development',db_sha256=r['sha256'],vehicle_wire_sha256=r['vehicle_wire_sha256'],
          topics=[dict(name=n,type=v) for n,v in topics],combined_reference_present=any(n=='/localization/kinematic_state' for n,v in topics),
          decoder_comparisons=checks,streams=st,teacher_rows=n,paired_rows=int(paired.sum()),
          raw_agreed_rows=int(t['raw_agree'].sum()),accepted_rows=int(t['accepted'].sum()),
          ambiguous_rows=int(np.sum(t['state']==1)),missing_rows=int(np.sum(t['state']==2)),
          coverage=float(t['accepted'].mean()) if n else None,
          coverage_among_pairs=float(t['accepted'][paired].mean()) if paired.any() else None,
          reason_counts={name:int(np.sum(t['reason_bits']&bit!=0)) for name,bit in REASONS.items()},
          flag_counts={name:int(np.sum(t['flag_bits']&bit!=0)) for name,bit in FLAGS.items()},
          exact_zero_vs_gt2=int(np.sum((t['flag_bits']&FLAGS['EXACT_PAIR']!=0)&(t['flag_bits']&FLAGS['ZERO_VS_GT2']!=0))),
          accepted_both_zero=int(np.sum(t['accepted']&(t['flag_bits']&FLAGS['BOTH_ZERO']!=0))),
          array_file='arrays/'+bag+'.npz',array_sha256=sha(filename),zero_episodes=zero_episodes(t,raw))
        if n:
            assert item['accepted_rows']+item['ambiguous_rows']+item['missing_rows']==n
            assert np.all(np.isfinite(t['speed_mps'][t['accepted']])) and np.all(np.isnan(t['speed_mps'][~t['accepted']]))
            for key in ('master_index','rover_index'):
                idx=t[key][t[key]>=0];assert len(idx)==len(set(idx)), 'Reused receiver message'
        witnesses+=examples(bag,t,raw,by_id,out);save_json(out/'bags'/(bag+'.json'),item);bags.append(item)
        print(bag,'labels',item['accepted_rows'],'/',n,'exact zero/>2',item['exact_zero_vs_gt2'],flush=True)
    save_json(out/'EXAMPLES.json',witnesses)
    groups=[]
    for g in sorted(set(b['group'] for b in bags)):
        rows=[b for b in bags if b['group']==g];n=sum(b['teacher_rows'] for b in rows);a=sum(b['accepted_rows'] for b in rows)
        groups.append(dict(group=g,label=rows[0]['label'],fold=rows[0]['fold'],bags=len(rows),teacher_rows=n,
           accepted_rows=a,coverage=a/n if n else None,raw_agreed_rows=sum(b['raw_agreed_rows'] for b in rows),
           ambiguous_rows=sum(b['ambiguous_rows'] for b in rows),missing_rows=sum(b['missing_rows'] for b in rows),
           reason_counts={k:sum(b['reason_counts'][k] for b in rows) for k in REASONS}))
    totals={k:sum(b[k] for b in bags) for k in ('decoder_comparisons','teacher_rows','paired_rows','raw_agreed_rows',
                'accepted_rows','ambiguous_rows','missing_rows','exact_zero_vs_gt2','accepted_both_zero')}
    totals['raw_messages']={name:sum(b['streams'][name]['messages'] for b in bags) for name in TOPIC_KEYS}
    totals['flag_counts']={k:sum(b['flag_counts'][k] for b in bags) for k in FLAGS}
    totals['reason_counts']={k:sum(b['reason_counts'][k] for b in bags) for k in REASONS}
    eligible={f:[g for g in groups if g['fold']==f and g['accepted_rows']>0] for f in ('fit','check')}
    passed=(len(eligible['fit'])>=3 and len(eligible['check'])>=2 and
      all({g['label'] for g in eligible[f]}=={'30618','30639'} for f in ('fit','check'))) if args.role=='train' else None
    result=dict(role=args.role,bags=len(bags),source_groups=len(groups),totals=totals,
      eligible_fit_groups=len(eligible['fit']),eligible_check_groups=len(eligible['check']),
      coverage_requirement_passed=passed,scientific_verdict='COMPONENT_READY' if passed else 'AUDIT_COMPLETE',
      proxy_only=True,runtime_gain=None,ready_to_merge=False,validation_opened=False,test_opened=False,
      zero_gnss_bags=[b['bag'] for b in bags if b['decoder_comparisons']==0],
      mean_group_coverage=float(np.mean([g['coverage'] for g in groups if g['coverage'] is not None])) if any(g['coverage'] is not None for g in groups) else None,
      official_reference_present_bags=[b['bag'] for b in bags if b['combined_reference_present']])
    save_json(out/'GROUPS.json',groups);save_json(out/'SUMMARY.json',result)
    import csv
    for name,rows,keys in [('per_bag.csv',bags,['bag','group','label','fold','teacher_rows','paired_rows','accepted_rows','ambiguous_rows','missing_rows','coverage','exact_zero_vs_gt2','accepted_both_zero']),
                           ('per_group.csv',groups,['group','label','fold','bags','teacher_rows','accepted_rows','ambiguous_rows','missing_rows','coverage'])]:
        with (out/name).open('x',newline='') as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:x.get(k) for k in keys} for x in rows)
    print(json.dumps(result,ensure_ascii=False),flush=True)

TOPIC_KEYS=('master_vel','rover_vel','master_fix','rover_fix')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--role',choices=['train','development'],required=True)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--freeze',type=Path)
    p.add_argument('--source-commit',required=True);run(p.parse_args())
