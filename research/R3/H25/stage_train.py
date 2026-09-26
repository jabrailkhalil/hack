"""Download the pinned opaque organizer archive; unpack TRAIN DBs only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('pinned_download', ROOT/'tools/get_dataset.py')
pin = importlib.util.module_from_spec(spec); spec.loader.exec_module(pin)


def main():
    folder = ROOT/'dataset'; folder.mkdir(exist_ok=True)
    (folder/'COLCON_IGNORE').touch()
    archive = folder/'dataset.zip'
    if not archive.exists():
        query = urllib.parse.urlencode(dict(public_key=pin.KEY, path='/dataset.zip'))
        with urllib.request.urlopen(pin.API+'?'+query, timeout=30) as r:
            url = json.load(r)['href']
        partial = archive.with_suffix('.part')
        try:
            with urllib.request.urlopen(url, timeout=60) as r, partial.open('wb') as out:
                total = 0
                while chunk := r.read(1024*1024):
                    total += len(chunk)
                    if total > 300*1024*1024:
                        raise ValueError('Oversize archive')
                    out.write(chunk)
            partial.replace(archive)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
    digest = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
    if digest != pin.SHA256:
        raise ValueError('Organizer archive changed')
    plan = json.loads((ROOT/'research/plan_v3.json').read_text())
    train = set(plan['splits']['train'])
    dest = folder/'data'; dest.mkdir(exist_ok=True)
    datazip = folder/'data-inner.zip'
    with zipfile.ZipFile(archive) as outer:
        with outer.open('data.zip') as inp, datazip.open('wb') as out:
            shutil.copyfileobj(inp, out, 1024*1024)
    extracted = []
    with zipfile.ZipFile(datazip) as inner:
        for bag in sorted(train):
            path = bag+'/'+bag+'_0.db3'
            target = dest/path
            if target.exists():
                raise FileExistsError('Do not overwrite staged data: '+str(target))
            target.parent.mkdir(parents=True, exist_ok=True)
            with inner.open(path) as inp, target.open('wb') as out:
                shutil.copyfileobj(inp, out, 1024*1024)
            extracted.append(bag)
    assert set(extracted) == train
    assert not any((dest/b).exists() for role in ('development','validation','test') for b in plan['splits'][role])
    print(json.dumps(dict(archive_sha256=digest, extracted_role='train', bags=len(extracted),
                         development_unpacked=False, validation_unpacked=False, test_unpacked=False)))


if __name__ == '__main__':
    main()
