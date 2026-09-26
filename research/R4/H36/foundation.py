"""R4-H36 source-checked, train-only rank/excitation gate. No candidate fitting."""
import argparse
from dataclasses import asdict
import datetime
import json
import os
from pathlib import Path
import platform
import sys
import time
from model import (ROOT, BASE, TREE, PLAN_SHA, DT, WARM, STEPS, ev, np,
                   sha, save, profile, theta0, physical, rank_report)


def integrity():
    receipt = json.loads((Path(__file__).parent/'SOURCE_RECEIPT.json').read_text())
    assert receipt['source_status']=='VERIFIED' and receipt['actual_git_tree']==TREE
    for f in receipt['files']:
        p=ROOT/f['path']
        if sha(p)!=f['sha256'] or bool(p.stat().st_mode & 0o111)!=(f['mode']=='100755'):
            raise ValueError('Changed original bytes/mode: '+f['path'])
    return dict(original_files_checked=len(receipt['files']),baseline_tree=TREE,passed=True)


def metadata():
    store=ev.ex.Store()
    groups=sorted({r['group'] for r in store.records.values() if r['split']=='train'},
                  key=lambda g:__import__('hashlib').sha256(('R4-H36:'+g).encode()).hexdigest())
    return dict(check=groups[:7],fitting=groups[7:])


def prepared(events, bag, group):
    grid=ev.ex.grid_channels(events,DT)
    if grid is None:
        return [],dict(bag=bag,eligible=0,selected=0)
    t,u,f,r,valid=grid
    stamps=[]
    for ch in (1,2):
        a=events[events[:,1]==ch][:,[0,2]]
        a=a[np.argsort(a[:,0],kind='stable')]
        _,idx=np.unique(a[:,0],return_index=True);a=a[idx]
        j=np.searchsorted(a[:,0],t,side='right')-1
        stamps.append(np.where(j>=0,a[np.maximum(j,0),0],-np.inf))
    v=(f+r)/2
    good=valid & (np.abs(f-r)<=.15) & (v>.5) & (v<35) & (np.abs(u)<=1)
    good &= np.abs(stamps[0]-stamps[1])<=.1
    choices=[]
    for anchor in range(200,len(t)-100,100):
        begin=anchor-WARM;end=anchor+100
        if not np.all(good[begin:end+1]):continue
        endpoints=np.arange(anchor,end+1,10)
        if any(np.any(np.diff(s[endpoints])<=0) for s in stamps):continue
        phase='traction' if u[anchor]>.04 else 'braking' if u[anchor]<-.04 else 'coast'
        command_range=float(np.ptp(u[anchor:end+1]))
        choices.append((phase,-command_range,anchor))
    chosen=[]
    for ph in ('traction','braking','coast'):
        selected=sorted(x for x in choices if x[0]==ph)[:4]
        for _,negative_range,a in selected:
            window_u=u[a-WARM:a+101].copy();window_v=v[a-WARM:a+101].copy()
            endpoints=window_v[WARM::10]
            meta=dict(bag=bag,group=group,phase=ph,anchor_s=float(t[a]),
                      command_range=-negative_range,mean_speed=float(window_v[WARM:].mean()))
            chosen.append(dict(u=window_u,v=window_v,y=np.diff(endpoints),meta=meta))
    stats=dict(bag=bag,group=group,eligible=len(choices),selected=len(chosen),
               eligible_by_phase={p:sum(x[0]==p for x in choices) for p in ('traction','braking','coast')})
    return chosen,stats


def as_data(rows):
    return dict(u=np.array([r['u'] for r in rows]),v=np.array([r['v'] for r in rows]),
                y=np.array([r['y'] for r in rows]),meta=[r['meta'] for r in rows])


def run(data_root, output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    check=integrity();split=metadata();cfg,readout=profile()
    save(output/'started.json',dict(baseline=BASE,tree=TREE,plan_commit=PLAN_SHA,
        utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),python=platform.python_version(),
        numpy=np.__version__,source_ref=os.environ.get('H36_SOURCE_SHA','local-uncommitted'),
        code_sha256={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},
        actual_class='reserve_odometry.guarded_readout.GuardedReadoutObserver',
        runtime_file=sys.modules['reserve_odometry.guarded_readout'].__file__,
        config=asdict(cfg),readout=asdict(readout),integrity=check,
        candidate_implemented=False,validation_opened=False,test_opened=False))
    save(output/'groups.json',split)  # BEFORE any bag is opened.
    start=time.perf_counter();all_rows=[];inventory=[];store=ev.ex.Store(data_root)
    for bag in store.plan['splits']['train']:
        events,refs=store.load(bag,'train')
        assert not any(refs.values())
        rows,stats=prepared(events,bag,store.records[bag]['group'])
        all_rows.extend(rows);inventory.append(stats)
        print('TRAIN_WINDOWS',bag,stats['eligible'],stats['selected'],flush=True)
    save(output/'access.json',dict(validation_opened=False,test_opened=False,access=store.access))
    save(output/'inventory.json',inventory)
    results={};reasons=[]
    for role in ('fitting','check'):
        rows=[r for r in all_rows if r['meta']['group'] in split[role]]
        if not rows:
            results[role]=dict(passed=False,windows=0)
            reasons.append(role+':empty');continue
        data=as_data(rows)
        np.savez_compressed(output/(role+'.npz'),u=data['u'],v=data['v'],y=data['y'])
        save(output/(role+'-windows.json'),data['meta'])
        report=rank_report(theta0(),data)
        report['command_excited_windows']=sum(m['command_range']>=.1 for m in data['meta'])
        report['command_excited_groups']=len({m['group'] for m in data['meta'] if m['command_range']>=.1})
        if len(rows)<(20 if role=='fitting' else 5):report['passed']=False
        results[role]=report
        if not report['passed']:reasons.append(role+':projected_rank_or_coverage')
    result=dict(baseline=BASE,foundation_passed=not reasons,rejection_reasons=reasons,
        train_bags=len(inventory),windows=len(all_rows),elapsed_s=time.perf_counter()-start,
        roles=results,fit_calls=0,validation_opened=False,test_opened=False)
    save(output/'result.json',result)
    print(json.dumps(result,indent=2),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    run(args.data_root,args.output)
