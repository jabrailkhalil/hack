"""Stage only fixed development DB members; do not decompress other roles."""
import argparse, hashlib, io, json, sys, urllib.parse, urllib.request, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import get_dataset as gd

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['development'],required=True)
    p.add_argument('--journal',type=Path,required=True);a=p.parse_args()
    plan=json.loads((ROOT/'research/plan_v3.json').read_text())
    records={r['bag']:r for r in json.loads((ROOT/'research/split_v3.json').read_text())['records']}
    members=plan['splits'][a.stage]
    if any(records[b]['split']!=a.stage for b in members):raise PermissionError('Role mismatch')
    directory=ROOT/'dataset';directory.mkdir(exist_ok=True);(directory/'COLCON_IGNORE').touch()
    archive=directory/'dataset.zip'
    if not archive.exists():
        query=urllib.parse.urlencode(dict(public_key=gd.KEY,path='/dataset.zip'))
        with urllib.request.urlopen(gd.API+'?'+query,timeout=30) as response:url=json.load(response)['href']
        part=archive.with_suffix('.part')
        try:
            with urllib.request.urlopen(url,timeout=60) as response,part.open('wb') as out:
                total=0
                while chunk:=response.read(1024*1024):
                    total+=len(chunk)
                    if total>300*1024*1024:raise ValueError('Oversized archive')
                    out.write(chunk)
            part.replace(archive)
        finally:part.unlink(missing_ok=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=gd.SHA256:raise ValueError('Wrong organizer archive')
    with zipfile.ZipFile(archive) as outer:data=outer.read('data.zip')
    extracted=[]
    with zipfile.ZipFile(io.BytesIO(data)) as inner:
        for bag in members:
            raw=inner.read(bag+'/'+bag+'_0.db3')
            if hashlib.sha256(raw).hexdigest()!=records[bag]['sha256']:raise ValueError('DB hash mismatch')
            path=directory/'data'/bag/(bag+'_0.db3');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            extracted.append(dict(bag=bag,role=a.stage,sha256=records[bag]['sha256']))
    a.journal.parent.mkdir(parents=True,exist_ok=True)
    a.journal.write_text(json.dumps(dict(archive_sha256=gd.SHA256,stage=a.stage,extracted=extracted,
      test_payload_decompressed=False,validation_payload_decompressed=False,train_payload_decompressed=False),indent=2)+'\n')
    print('Staged only',a.stage,len(extracted),'bags',flush=True)
if __name__=='__main__':main()
