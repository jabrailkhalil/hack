"""Fresh canonical v8 replay on a verified development export; no H39 candidate."""
import argparse
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import zipfile
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools/finalization'),str(ROOT/'tools/research_v6'),str(ROOT/'src/reserve_odometry'),str(Path(__file__).parent)]
import evaluate as ev
import compare as v6
import foundation
from reserve_odometry.core import Config
from reserve_odometry.guarded_readout import GuardedReadoutObserver,ReadoutConfig
EXPECTED_ZIP='5a840289a44b90d118847b33cdab2d3820ede3d92678bef350ed475f40c47fce'


def run(archive,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    foundation.verify_sources()
    if ev.sha(archive)!=EXPECTED_ZIP:raise ValueError('Development export ZIP mismatch')
    profile=json.loads((ROOT/'src/reserve_odometry/config/champion_v8.json').read_text())
    cfg=Config(**profile['config']);readout=ReadoutConfig(**profile['readout'])
    ev.Observer=lambda c:GuardedReadoutObserver(c,readout=readout)
    models={'baseline_v2':cfg,'balanced_physics':Config(**asdict(cfg))}
    ops={'rate_hz':20.,'alignment_delay_s':0.}
    store=ev.ex.Store();clean=[];stress=[];access=[];start=time.perf_counter()
    ev.save(output/'started.json',{'stage':'development-baseline-only','candidate_implemented':False,
        'baseline_sha':'e3b0c9c039d2953fbfcda51231263d38ef9f1024','class':'GuardedReadoutObserver',
        'class_file':sys.modules[GuardedReadoutObserver.__module__].__file__,'config':asdict(cfg),
        'readout':asdict(readout),'operational':ops,'source_hashes':ev.protected_files(),
        'runner_sha256':ev.sha(__file__),'export_zip_sha256':EXPECTED_ZIP,
        'labels':'both legacy model labels create v8: second is duplicate baseline, NOT H39',
        'test_opened':False,'validation_opened':False})
    with zipfile.ZipFile(archive) as z:
        manifest={r['bag']:r for r in json.loads(z.read('access.json'))}
        if set(manifest)!=set(store.plan['splits']['development']):raise ValueError('Export role membership mismatch')
        for bag in store.plan['splits']['development']:
            row=store.records[bag];m=manifest[bag]
            if row['split']!='development' or m['purpose']!='development' or row['sha256']!=m['sha256'] or row['group']!=m['group']:
                raise PermissionError('Wrong role/bag hash')
            payload=z.read('development/'+bag+'.npz')
            if hashlib.sha256(payload).hexdigest()!=m['export_sha256']:raise ValueError('Export bytes mismatch')
            with ev.np.load(io.BytesIO(payload),allow_pickle=False) as a:
                events=a['events'];refs={r:a[r].tolist() for r in ['master','rover']}
            meta={'bag':bag,'group':row['group']}
            c=dict(**meta,**ev.score(events,refs,models,ops));clean.append(c);faults=[]
            grid=ev.ex.grid_channels(events)
            if grid is not None:
                t,u,f,r,valid=grid
                indices=ev.np.flatnonzero(valid&((f+r)/2>2.)&(t>max(25.,.1*t[-1]))&(t<t[-1]-25.))
                if len(indices):
                    anchor=float(t[indices[0]])
                    for kind,duration in [('bias',5.),('dropout',5.),('dropout',10.),('lock',3.)]:
                        fault={'kind':kind,'start':anchor,'end':anchor+duration}
                        window=events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]
                        s=dict(**meta,fault=fault,**ev.score(window,refs,models,ops,fault));faults.append(s);stress.append(s)
            access.append(m)
            ev.save(output/'bags'/(bag+'.json'),{'clean':c,'stress':faults})
            ev.save(output/'access.json',access)
            print('DEVELOPMENT BASELINE',bag,flush=True)
    summary=v6.summary(clean,stress,'baseline_v2')
    expected={'clean_rmse':.09266814298282507,'fault_rmse':.2375486120563008,
        'pooled_rmse':.1293056944774334,'distance_rmse':5.310295004801444,'samples':394221}
    delta={k:summary[k]-v for k,v in expected.items()}
    if any(abs(v)>1e-10 for v in delta.values()):raise AssertionError(('Fingerprint mismatch',delta))
    for row in clean+stress:
        if row['runtime']['baseline_v2']!=row['runtime']['balanced_physics']:raise AssertionError('Duplicate counters mismatch')
        for scores in row['receivers'].values():
            for k,v in scores['baseline_v2'].items():
                if scores['balanced_physics'][k]!=v:raise AssertionError('Duplicate metrics mismatch')
    ev.save(output/'results.json',{'clean':clean,'stress':stress,'summary':summary,
        'elapsed_wall_s':time.perf_counter()-start,'fingerprint_delta':delta,
        'clean_bags':len(clean),'original_faults':len(stress),'candidate_accuracy_evaluated':False,
        'causal_errors':sum(r['runtime']['baseline_v2']['causal_errors'] for r in clean+stress),
        'resets':sum(r['runtime']['baseline_v2']['resets'] for r in clean+stress)})
    ev.save(output/'HASHES.json',{str(p.relative_to(output)):ev.sha(p) for p in sorted(output.rglob('*')) if p.is_file() and p.name!='HASHES.json'})
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--export',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();run(a.export,a.output)
