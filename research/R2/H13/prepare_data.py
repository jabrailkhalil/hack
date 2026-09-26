"""Verify pinned organizer ZIP; extract only named non-test roles, never all bags."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import get_dataset as source

def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--roles',nargs='+',required=True,choices=['train','development','validation']);p.add_argument('--journal',type=Path,required=True)
    args=p.parse_args()
    if 'validation' in args.roles:
        import os,subprocess
        commit=os.environ.get('H13_FREEZE_COMMIT')
        if not commit: raise PermissionError('Publish freeze before extracting validation')
        subprocess.run(['git','cat-file','-e',commit+'^{commit}'],cwd=ROOT,check=True)
    plan=json.loads((ROOT/'research/plan_v3.json').read_text()); names={b for r in args.roles for b in plan['splits'][r]}
    dest=ROOT/'dataset'; dest.mkdir(exist_ok=True);(dest/'COLCON_IGNORE').touch()
    archive=dest/'dataset.zip'
    if not archive.exists():
        q=urllib.parse.urlencode(dict(public_key=source.KEY,path='/dataset.zip'))
        with urllib.request.urlopen(source.API+'?'+q,timeout=30) as r: url=json.load(r)['href']
        temp=archive.with_suffix('.part')
        try:
            with urllib.request.urlopen(url,timeout=90) as inp,temp.open('wb') as out:
                total=0
                while b:=inp.read(1048576):
                    total+=len(b)
                    if total>300*1024**2: raise ValueError('Oversize archive')
                    out.write(b)
            temp.replace(archive)
        finally: temp.unlink(missing_ok=True)
    if digest(archive)!=source.SHA256: raise ValueError('Dataset changed')
    inner=dest/'data.zip'
    if not inner.exists():
        with zipfile.ZipFile(archive) as z:
            options=[n for n in z.namelist() if Path(n).name=='data.zip']
            if len(options)!=1: raise ValueError('Ambiguous data archive')
            with z.open(options[0]) as f,inner.open('wb') as o: shutil.copyfileobj(f,o)
    extracted=[]
    with zipfile.ZipFile(inner) as z:
        for item in z.infolist():
            parts=Path(item.filename).parts
            bags=set(parts)&names
            if item.is_dir() or not bags: continue
            if len(bags)!=1 or '..' in parts or Path(item.filename).is_absolute(): raise ValueError('Unsafe entry')
            bag=bags.pop(); index=parts.index(bag)
            path=dest/'data'/Path(*parts[index:]); path.parent.mkdir(parents=True,exist_ok=True)
            with z.open(item) as f,path.open('wb') as o: shutil.copyfileobj(f,o)
            extracted.append(str(path.relative_to(ROOT)))
    records={r['bag']:r for r in json.loads((ROOT/'research/split_v3.json').read_text())['records']}
    for bag in names:
        if digest(dest/'data'/bag/(bag+'_0.db3'))!=records[bag]['sha256']: raise ValueError('DB checksum '+bag)
    args.journal.parent.mkdir(parents=True,exist_ok=True)
    args.journal.write_text(json.dumps(dict(roles=args.roles,dataset_sha256=source.SHA256,extracted=extracted,test_payloads_extracted=False),indent=2)+'\n')
    print('Verified and selectively extracted',len(names),'bags',args.roles,flush=True)
if __name__=='__main__':main()
