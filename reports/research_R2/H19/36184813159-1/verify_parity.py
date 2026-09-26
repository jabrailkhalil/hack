"""Compare completed local/export and remote/SQLite H19 evidence exactly."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np

def verify(a,b,out):
 a,b=Path(a),Path(b);stats=dict(numeric_fields=0,max_absolute_difference=0.,arrays=0,array_elements=0)
 def walk(x,y,p=''):
  if type(x)!=type(y): raise AssertionError(('type',p,type(x),type(y)))
  if isinstance(x,dict):
   assert x.keys()==y.keys(),p
   for k in x:walk(x[k],y[k],p+'/'+k)
  elif isinstance(x,list):
   assert len(x)==len(y),p
   for i,(v,w) in enumerate(zip(x,y)):walk(v,w,p+'/'+str(i))
  elif isinstance(x,(int,float)) and not isinstance(x,bool):
   stats['numeric_fields']+=1; delta=abs(x-y);stats['max_absolute_difference']=max(stats['max_absolute_difference'],delta)
   assert delta==0,(p,x,y)
  else:assert x==y,(p,x,y)
 for f in ('results.json','decision.json'):walk(json.loads((a/f).read_text()),json.loads((b/f).read_text()),f)
 for f in sorted((a/'traces').glob('*.npz')):
  with np.load(f,allow_pickle=False) as x,np.load(b/'traces'/f.name,allow_pickle=False) as y:
   assert set(x.files)==set(y.files)
   for k in x.files:
    assert np.array_equal(x[k],y[k]),(f.name,k)
    stats['arrays']+=1;stats['array_elements']+=x[k].size
 sa=json.loads((a/'started.json').read_text());sb=json.loads((b/'started.json').read_text())
 keys=[k for k in sa['source_sha256'] if k.endswith('.py') or k.endswith('.patch') or k in ('research/split_v3.json','src/reserve_odometry/config/guarded_readout_v7.json')]
 for k in keys:assert sa['source_sha256'][k]==sb['source_sha256'][k],k
 assert sa['candidate_core_sha256']==sb['candidate_core_sha256']
 stats.update(passed=True,source_code_files_compared=len(keys),candidate_core_sha256=sb['candidate_core_sha256'],
              local_source_commit_label=sa['source_commit'],remote_measured_commit=sb['source_commit'],
              explanation='Local working tree started from source-export commit; algorithm/driver bytes checked against committed remote code. Reports/PLAN presence differs, not algorithm.')
 Path(out).write_text(json.dumps(stats,indent=2)+'\n');print(json.dumps(stats,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('local');p.add_argument('remote');p.add_argument('output');x=p.parse_args();verify(x.local,x.remote,x.output)
