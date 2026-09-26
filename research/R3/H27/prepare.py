"""Download pinned archive; extract ONLY train/development DB entries."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile
from common import ROOT, save, sha
sys.path.insert(0,str(ROOT/'tools'))
import get_dataset as dl


def main():
    target=ROOT/'dataset';target.mkdir(exist_ok=True);(target/'COLCON_IGNORE').touch()
    archive=target/'dataset.zip'
    if not archive.exists():
        query=urllib.parse.urlencode(dict(public_key=dl.KEY,path='/dataset.zip'))
        with urllib.request.urlopen(dl.API+'?'+query,timeout=30) as r: url=json.load(r)['href']
        with urllib.request.urlopen(url,timeout=60) as r, archive.with_suffix('.part').open('wb') as out:
            size=0
            while chunk:=r.read(1024*1024):
                size+=len(chunk)
                if size>300*1024*1024: raise ValueError('Archive too large')
                out.write(chunk)
        archive.with_suffix('.part').replace(archive)
    if sha(archive)!=dl.SHA256: raise ValueError('Archive checksum')
    inner=target/'data.zip'
    with zipfile.ZipFile(archive) as z:
        name=next(x for x in z.namelist() if x=='data.zip')
        with z.open(name) as src,inner.open('wb') as dst: shutil.copyfileobj(src,dst)
    plan=json.loads((ROOT/'research/plan_v3.json').read_text())
    records={r['bag']:r for r in json.loads((ROOT/'research/split_v3.json').read_text())['records']}
    extracted=[]
    with zipfile.ZipFile(inner) as z:
        names=set(z.namelist())
        for role in ('train','development'):
            for bag in plan['splits'][role]:
                suffix=bag+'/'+bag+'_0.db3'
                matches=[x for x in names if x==suffix or x.endswith('/'+suffix)]
                if len(matches)!=1: raise ValueError('Missing/ambiguous bag member '+bag)
                out=target/'data'/suffix;out.parent.mkdir(parents=True,exist_ok=True)
                with z.open(matches[0]) as src,out.open('wb') as dst: shutil.copyfileobj(src,dst)
                if sha(out)!=records[bag]['sha256']: raise ValueError('Extracted bag checksum')
                extracted.append(dict(role=role,bag=bag,sha256=sha(out)))
    save(target/'H27-extraction.json',dict(archive_sha256=dl.SHA256,extracted=extracted,validation_extracted=False,test_extracted=False))
    print('Extracted only train/development:',len(extracted),flush=True)

if __name__=='__main__':main()
