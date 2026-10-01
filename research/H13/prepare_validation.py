"""Extract only validation databases from the checksum-pinned organizer ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[2]
ARCHIVE_SHA='d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52'
KEY='https://disk.yandex.ru/d/DdnscmWTBtzkOQ'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path)
    a=p.parse_args()
    cache=ROOT/'dataset';cache.mkdir(exist_ok=True);(cache/'COLCON_IGNORE').touch()
    archive=a.archive or cache/'organizer-pinned.zip'
    if not archive.exists():
        query=urllib.parse.urlencode({'public_key':KEY,'path':'/dataset.zip'})
        api='https://cloud-api.yandex.net/v1/disk/public/resources/download?'+query
        with urllib.request.urlopen(api,timeout=30) as r:url=json.load(r)['href']
        partial=archive.with_suffix('.part')
        try:
            with urllib.request.urlopen(url,timeout=60) as r,partial.open('wb') as w:
                size=0
                while chunk:=r.read(1024*1024):
                    size+=len(chunk)
                    if size>300*1024*1024:raise ValueError('Unexpected archive size')
                    w.write(chunk)
            partial.replace(archive)
        finally:partial.unlink(missing_ok=True)
    with archive.open('rb') as r:
        if hashlib.file_digest(r,'sha256').hexdigest()!=ARCHIVE_SHA:raise ValueError('Organizer ZIP changed')
    plan=json.loads((ROOT/'research/plan_v3.json').read_text())
    with tempfile.TemporaryFile() as inner:
        with zipfile.ZipFile(archive) as outer,outer.open('data.zip') as source:
            shutil.copyfileobj(source,inner)
        inner.seek(0)
        with zipfile.ZipFile(inner) as z:
            for bag in plan['splits']['validation']:
                name=f'{bag}/{bag}_0.db3'
                target=cache/'data'/name;target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(name) as r,target.open('wb') as w:shutil.copyfileobj(r,w)
    print('VALIDATION_ONLY_EXTRACTED',len(plan['splits']['validation']))
    print('No train, development or final-test database payload extracted')

if __name__=='__main__':main()
