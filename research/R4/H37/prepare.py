"""Exact pinned downloader API; only train and development DBs extracted."""
import argparse, json, shutil, sys, urllib.parse, urllib.request, zipfile
from pathlib import Path
from common import ROOT,HERE,save,sha,pins
sys.path.insert(0,str(ROOT/'tools'))
import get_dataset as dl

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);save(a.output/'started.json',pins())
    target=ROOT/'dataset';target.mkdir(exist_ok=True);(target/'COLCON_IGNORE').touch()
    archive=target/'dataset.zip'
    if not archive.exists():
        query=urllib.parse.urlencode(dict(public_key=dl.KEY,path='/dataset.zip'))
        with urllib.request.urlopen(dl.API+'?'+query,timeout=30) as r:url=json.load(r)['href']
        with urllib.request.urlopen(url,timeout=60) as r,archive.with_suffix('.part').open('wb') as out:
            size=0
            while chunk:=r.read(1024*1024):
                size+=len(chunk)
                if size>300*1024*1024:raise ValueError('Archive too large')
                out.write(chunk)
        archive.with_suffix('.part').replace(archive)
    if sha(archive)!=dl.SHA256:raise ValueError('Organizer archive changed')
    inner=target/'data.zip'
    with zipfile.ZipFile(archive) as z:
        with z.open('data.zip') as src,inner.open('wb') as dst:shutil.copyfileobj(src,dst)
    plan=json.loads((ROOT/'research/plan_v3.json').read_text());extracted=[]
    records={r['bag']:r for r in json.loads((ROOT/'research/split_v3.json').read_text())['records']}
    with zipfile.ZipFile(inner) as z:
        names=z.namelist()
        for role in ('train','development'):
            for bag in plan['splits'][role]:
                suffix=bag+'/'+bag+'_0.db3';matches=[x for x in names if x==suffix or x.endswith('/'+suffix)]
                if len(matches)!=1:raise ValueError('Missing/ambiguous DB '+bag)
                out=target/'data'/suffix;out.parent.mkdir(parents=True,exist_ok=True)
                with z.open(matches[0]) as src,out.open('wb') as dst:shutil.copyfileobj(src,dst)
                if sha(out)!=records[bag]['sha256']:raise ValueError('DB checksum '+bag)
                extracted.append(dict(role=role,bag=bag,sha256=sha(out)))
    save(a.output/'extraction.json',dict(archive_sha256=sha(archive),split_sha256=sha(ROOT/'research/split_v3.json'),
         extracted=extracted,validation_extracted=False,test_extracted=False))
    print('Verified train/development DBs:',len(extracted),flush=True)
if __name__=='__main__':main()
