"""Use pinned organizer download; selectively extract train/development only."""
import argparse, hashlib, json, urllib.request, urllib.parse, zipfile, shutil
from pathlib import Path, PurePosixPath
from support import ROOT, save, sha
import sys
sys.path.insert(0,str(ROOT/'tools'))
import get_dataset as original

def run(role, directory):
    if role not in ('train','development'): raise PermissionError(role)
    directory.mkdir(parents=True, exist_ok=True);(directory/'COLCON_IGNORE').touch()
    archive=directory/'dataset.zip'
    if not archive.exists():
        query=urllib.parse.urlencode(dict(public_key=original.KEY,path='/dataset.zip'))
        with urllib.request.urlopen(original.API+'?'+query,timeout=30) as r: url=json.load(r)['href']
        partial=directory/'dataset.part'
        try:
            with urllib.request.urlopen(url,timeout=60) as r,partial.open('wb') as out:
                total=0
                while chunk:=r.read(1024*1024):
                    total+=len(chunk)
                    if total>300*1024*1024:raise ValueError('Oversized organizer archive')
                    out.write(chunk)
            partial.rename(archive)
        except Exception:
            partial.unlink(missing_ok=True);raise
    if sha(archive)!=original.SHA256:raise ValueError('Organizer ZIP hash mismatch')
    inner=directory/'data.zip'
    with zipfile.ZipFile(archive) as z:
        members=[i for i in z.infolist() if PurePosixPath(i.filename).name=='data.zip']
        if len(members)!=1:raise ValueError('Expected unique inner archive')
        with z.open(members[0]) as src,inner.open('wb') as out:shutil.copyfileobj(src,out)
    plan=json.loads((ROOT/'research/plan_v3.json').read_text()); names=set(plan['splits'][role])
    manifest=json.loads((ROOT/'research/split_v3.json').read_text())
    records={r['bag']:r for r in manifest['records']};extracted=[]
    with zipfile.ZipFile(inner) as z:
        for i in z.infolist():
            p=PurePosixPath(i.filename)
            if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe inner path')
            if i.is_dir():continue
            name=p.name
            if not name.endswith('_0.db3'):continue
            bag=name[:-6]
            if bag not in names:continue
            if records[bag]['split']!=role:raise PermissionError('Role mismatch')
            outpath=directory/'data'/bag/name;outpath.parent.mkdir(parents=True,exist_ok=True)
            with z.open(i) as src,outpath.open('wb') as out:shutil.copyfileobj(src,out)
            if sha(outpath)!=records[bag]['sha256']:raise ValueError('Bag hash mismatch: '+bag)
            extracted.append(bag)
    if sorted(extracted)!=sorted(names):raise ValueError('Incomplete role extraction')
    save(directory/('staged_'+role+'.json'),dict(role=role,bags=extracted,
        dataset_sha256=original.SHA256,validation_extracted=False,test_extracted=False))
    print('STAGED',role,len(extracted),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--role',choices=['train','development'],required=True)
    p.add_argument('--directory',type=Path,default=ROOT/'dataset');a=p.parse_args();run(a.role,a.directory)
