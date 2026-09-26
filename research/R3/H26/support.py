"""Provenance, selective TRAIN extraction and compact evidence (not an evaluator)."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
BASE='e3b0c9c039d2953fbfcda51231263d38ef9f1024'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def manifest():
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE,'--','src','tools',
          'research/plan_v3.json','research/split_v3.json','requirements-research.txt'],cwd=ROOT,text=True).splitlines()
    hashes={}
    for name in sorted(names):
        original=subprocess.check_output(['git','show',BASE+':'+name],cwd=ROOT)
        current=(ROOT/name).read_bytes()
        if current!=original:raise ValueError('Changed pinned source: '+name)
        hashes[name]=hashlib.sha256(current).hexdigest()
    assert len(hashes)==57
    target=HERE/'manifest.json';result=dict(baseline=BASE,sha256=hashes)
    if target.exists() and json.loads(target.read_text())!=result:raise ValueError('Existing manifest differs')
    save(target,result)
    print('Verified original source/config/role files:',len(hashes))

def train(destination):
    sys.path.insert(0,str(ROOT/'tools'))
    import get_dataset as ds
    manifest()
    destination.mkdir(parents=True,exist_ok=False)
    records=json.loads((ROOT/'research/split_v3.json').read_text())['records']
    wanted={r['bag']:r for r in records if r['split']=='train'}
    with tempfile.TemporaryDirectory(prefix='R3-H26-data-') as tmp:
        outer=Path(tmp)/'dataset.zip'
        query=urllib.parse.urlencode(dict(public_key=ds.KEY,path='/dataset.zip'))
        with urllib.request.urlopen(ds.API+'?'+query,timeout=30) as response:
            url=json.load(response)['href']
        with urllib.request.urlopen(url,timeout=60) as response,outer.open('wb') as out:
            total=0
            while chunk:=response.read(1024*1024):
                total+=len(chunk)
                if total>300*1024*1024:raise ValueError('Oversized organizer archive')
                out.write(chunk)
        if sha(outer)!=ds.SHA256:raise ValueError('Outer organizer checksum differs')
        inner=Path(tmp)/'data.zip'
        with zipfile.ZipFile(outer) as z:
            names=[n for n in z.namelist() if Path(n).name=='data.zip']
            if len(names)!=1:raise ValueError('Ambiguous inner archive')
            with z.open(names[0]) as source,inner.open('wb') as out:shutil.copyfileobj(source,out)
        # Inspect names/metadata only; decompress only original train DB members.
        extracted=[]
        with zipfile.ZipFile(inner) as z:
            for bag,record in wanted.items():
                names=[n for n in z.namelist() if Path(n).name==bag+'_0.db3']
                if len(names)!=1:raise ValueError('Missing/ambiguous train DB '+bag)
                outpath=destination/bag/(bag+'_0.db3');outpath.parent.mkdir()
                with z.open(names[0]) as source,outpath.open('wb') as out:shutil.copyfileobj(source,out)
                if sha(outpath)!=record['sha256']:raise ValueError('Train checksum differs '+bag)
                extracted.append(bag)
    save(destination.parent/'train-preparation.json',dict(baseline=BASE,archive_sha256=ds.SHA256,
        extracted_train_bags=extracted,validation_extracted=False,test_extracted=False,
        payload_topics_read=False,scope='Archive selection only; SQL vehicle-only access is enforced by original Store'))
    print('Extracted only original train DBs:',len(extracted))

def inventory(directory):
    paths=[p for p in directory.rglob('*') if p.is_file() and p.name!='SHA256_MANIFEST.json']
    save(directory/'SHA256_MANIFEST.json',{str(p.relative_to(directory)):dict(sha256=sha(p),bytes=p.stat().st_size)
                                           for p in sorted(paths)})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['manifest','train','inventory']);p.add_argument('--path',type=Path)
    a=p.parse_args()
    if a.stage=='manifest':manifest()
    elif a.path is None:p.error('--path required')
    elif a.stage=='train':train(a.path)
    else:inventory(a.path)
