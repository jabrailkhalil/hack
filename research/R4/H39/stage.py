"""Pinned organizer download; extract ONLY train databases, never decode other roles."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import get_dataset as pinned


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def stage(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    plan = json.loads((ROOT/'research/plan_v3.json').read_text())
    split_path = ROOT/'research/split_v3.json'
    if sha(split_path) != plan['manifest_sha256']:
        raise ValueError('Split hash mismatch')
    records = {r['bag']: r for r in json.loads(split_path.read_text())['records']}
    bags = plan['splits']['train']
    if any(records[b]['split'] != 'train' for b in bags) or len(bags) != 64:
        raise PermissionError('Not the exact train role')
    archive = directory/'dataset.zip'
    query = urllib.parse.urlencode({'public_key': pinned.KEY, 'path': '/dataset.zip'})
    with urllib.request.urlopen(pinned.API+'?'+query, timeout=30) as f:
        href = json.load(f)['href']
    with urllib.request.urlopen(href, timeout=60) as f, archive.open('xb') as out:
        total = 0
        for block in iter(lambda: f.read(1024*1024), b''):
            total += len(block)
            if total > 300*1024*1024:
                raise ValueError('Oversized dataset')
            out.write(block)
    if sha(archive) != pinned.SHA256:
        raise ValueError('Organizer archive changed')
    inner = directory/'data.zip'
    with zipfile.ZipFile(archive) as outer:
        candidates = [n for n in outer.namelist() if PurePosixPath(n).name == 'data.zip']
        if len(candidates) != 1:
            raise ValueError('Expected exactly one data.zip')
        with outer.open(candidates[0]) as source, inner.open('xb') as target:
            for block in iter(lambda: source.read(1024*1024), b''):
                target.write(block)
    extracted = []
    with zipfile.ZipFile(inner) as data:
        for bag in bags:
            names = [n for n in data.namelist() if PurePosixPath(n).name == bag+'_0.db3']
            if len(names) != 1:
                raise ValueError('Missing or duplicate bag: '+bag)
            member = data.getinfo(names[0])
            if member.file_size != records[bag]['bytes']:
                raise ValueError('Bag size mismatch: '+bag)
            dest = directory/'data'/bag/(bag+'_0.db3')
            dest.parent.mkdir(parents=True)
            with data.open(member) as src, dest.open('xb') as dst:
                for block in iter(lambda: src.read(1024*1024), b''):
                    dst.write(block)
            if sha(dest) != records[bag]['sha256']:
                raise ValueError('Bag hash mismatch: '+bag)
            extracted.append({'bag': bag, 'role': 'train', 'sha256': sha(dest)})
    save(directory/'STAGING.json', {'dataset_sha256': pinned.SHA256,
        'extracted': extracted, 'measurement_decode_performed': False,
        'validation_extracted': False, 'test_extracted': False})
    return directory/'data'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    try:
        print(stage(args.output))
    except Exception as e:
        if args.output.exists():
            save(args.output/'STAGING_ERROR.json', {'error': type(e).__name__, 'detail': str(e)})
        raise
