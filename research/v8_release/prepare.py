"""Download pinned organizer archive; extract ONLY validation DBs, no final-test IO."""
from pathlib import Path
import hashlib
import io
import json
import shutil
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SHA = 'd0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52'
SPLIT_SHA = '20928a29daad2b4178ddb92e2a4d9ddb347952f6c03845802a8d82fff7da5ae0'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()

def prepare(archive, out):
    archive,out=Path(archive),Path(out)
    if sha(archive)!=SHA: raise ValueError('Organizer archive hash changed')
    split=ROOT/'research/split_v3.json'
    if sha(split)!=SPLIT_SHA: raise ValueError('Split changed')
    records={r['bag']:r for r in json.loads(split.read_text())['records']}
    bags=json.loads((ROOT/'research/plan_v3.json').read_text())['splits']['validation']
    if len(bags)!=19 or any(records[b]['split']!='validation' for b in bags):
        raise ValueError('Validation membership changed')
    out.mkdir(parents=True,exist_ok=False)
    (out/'COLCON_IGNORE').touch()
    receipt={'dataset_sha256':SHA,'role':'validation','test_extracted':False,'files':[]}
    with zipfile.ZipFile(archive) as outer:
        names=[n for n in outer.namelist() if n.rstrip('/').endswith('data.zip')]
        if len(names)!=1: raise ValueError('Expected exactly one nested data.zip')
        inner_path=out/'data.zip'
        with outer.open(names[0]) as source,inner_path.open('wb') as target: shutil.copyfileobj(source,target)
    with zipfile.ZipFile(inner_path) as z:
        for bag in bags:
            for suffix in (bag+'_0.db3','metadata.yaml'):
                member=bag+'/'+suffix
                if z.namelist().count(member)!=1: raise ValueError('Missing/duplicate member '+member)
                target=out/'data'/member; target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(member) as source,target.open('wb') as dest: shutil.copyfileobj(source,dest)
                digest=sha(target)
                if suffix.endswith('.db3') and digest!=records[bag]['sha256']: raise ValueError('DB hash '+bag)
                receipt['files'].append({'path':member,'sha256':digest})
    inner_path.unlink()
    (out/'RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not a.archive.exists():
        query=urllib.parse.urlencode({'public_key':'https://disk.yandex.ru/d/DdnscmWTBtzkOQ','path':'/dataset.zip'})
        with urllib.request.urlopen('https://cloud-api.yandex.net/v1/disk/public/resources/download?'+query,timeout=30) as f: url=json.load(f)['href']
        a.archive.parent.mkdir(parents=True,exist_ok=True)
        with urllib.request.urlopen(url,timeout=60) as inp,a.archive.open('wb') as out:
            size=0
            while block:=inp.read(1<<20):
                size+=len(block)
                if size>300*(1<<20):raise ValueError('Archive size exceeds budget')
                out.write(block)
    print(json.dumps(prepare(a.archive,a.output),indent=2))
