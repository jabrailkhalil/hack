"""Download the pinned compressed archive; unpack only the authorized role.

Unlike the general get_dataset.py command, never decompress a test/train DB.
No measurement parsing here. Decoder access is independently role-checked.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request
import zipfile
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import get_dataset as gd


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--stage',choices=['development','validation'],required=True)
    p.add_argument('--journal',type=Path,required=True)
    a=p.parse_args()
    plan=json.loads((ROOT/'research/plan_v3.json').read_text())
    manifest=json.loads((ROOT/'research/split_v3.json').read_text())
    members=plan['splits'][a.stage];records={r['bag']:r for r in manifest['records']}
    if any(records[bag]['split']!=a.stage for bag in members):raise PermissionError('Role mismatch')
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
    extracted=[]
    with zipfile.ZipFile(archive) as outer:
        data=outer.read('data.zip')
    with zipfile.ZipFile(io.BytesIO(data)) as inner:
        for bag in members:
            name=bag+'/'+bag+'_0.db3'
            # No other DB member is opened or decompressed, including validation
            # at development stage. Reading ZIP directory metadata is not SQL IO.
            raw=inner.read(name)
            if hashlib.sha256(raw).hexdigest()!=records[bag]['sha256']:raise ValueError('DB hash mismatch')
            path=directory/'data'/bag/(bag+'_0.db3');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            extracted.append(dict(bag=bag,role=a.stage,sha256=records[bag]['sha256']))
    a.journal.parent.mkdir(parents=True,exist_ok=True)
    a.journal.write_text(json.dumps(dict(archive_sha256=gd.SHA256,stage=a.stage,extracted=extracted,
        test_payload_decompressed=False,train_payload_decompressed=False),indent=2)+'\n')
    print('Staged only',a.stage,len(extracted),'bags',flush=True)

if __name__=='__main__':main()
