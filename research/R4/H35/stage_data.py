"""Extract only permitted role from the authorized H35 data artifact."""
import argparse,hashlib,io,json,zipfile
from pathlib import Path
from common import Store,save
ARTIFACT_SHA256='6c72b13301170e86706772e8a47df4676fa510dbf2c7598289a308ec604863d6'
def stage(artifact,out,role):
 if role not in ('train','development'):raise PermissionError('role not permitted')
 h=hashlib.sha256(artifact.read_bytes()).hexdigest()
 if h!=ARTIFACT_SHA256:raise ValueError('artifact hash mismatch')
 store=Store(out);dest=out/role
 if dest.exists():raise FileExistsError('preserve existing staged role')
 dest.mkdir(parents=True);receipt=[]
 with zipfile.ZipFile(artifact) as outer:
  with zipfile.ZipFile(io.BytesIO(outer.read('permitted.zip'))) as inner:
   for bag in store.plan['splits'][role]:
    row=store.records[bag];assert row['split']==role
    name=role+'/'+bag+'/'+bag+'_0.db3';payload=inner.read(name)
    h=hashlib.sha256(payload).hexdigest();assert h==row['sha256'],bag
    p=out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(payload)
    receipt.append(dict(bag=bag,role=role,sha256=h))
 save(dest/'STAGED.json',dict(artifact_sha256=ARTIFACT_SHA256,records=receipt,sql_decoded=False,test_extracted=False,validation_extracted=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--artifact',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--role',choices=['train','development'],required=True);a=p.parse_args();stage(a.artifact,a.output,a.role)
