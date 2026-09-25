#!/usr/bin/env python3
"""Download the exact audited organizer ZIP, verify SHA256, safely unpack locally."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.parse
import urllib.request
import zipfile

KEY = 'https://disk.yandex.ru/d/DdnscmWTBtzkOQ'
SHA256 = 'd0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52'
API = 'https://cloud-api.yandex.net/v1/disk/public/resources/download'


def unpack(archive, target, maximum):
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        if sum(i.file_size for i in source.infolist()) > maximum:
            raise ValueError('Unexpected uncompressed archive size')
        for entry in source.infolist():
            path = (target / entry.filename).resolve()
            if target not in path.parents:
                raise ValueError('Unsafe ZIP path')
            if entry.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as inp, path.open('wb') as out:
                shutil.copyfileobj(inp, out, 1024 * 1024)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('dataset'))
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    # Dataset includes a second copy of tram_vehicle_msgs; keep colcon out.
    (args.directory / 'COLCON_IGNORE').touch()
    destination = args.directory / 'dataset.zip'
    if not destination.exists():
        query = urllib.parse.urlencode(dict(public_key=KEY, path='/dataset.zip'))
        with urllib.request.urlopen(API + '?' + query, timeout=30) as response:
            url = json.load(response)['href']
        partial = destination.with_suffix('.part')
        try:
            with urllib.request.urlopen(url, timeout=60) as response, partial.open('wb') as out:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 300 * 1024 * 1024:
                        raise ValueError('Unexpected compressed archive size')
                    out.write(chunk)
            partial.replace(destination)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
    digest = hashlib.sha256()
    with destination.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != SHA256:
        raise ValueError('Dataset SHA256 changed; inspect new README before changing the pinned hash')
    unpack(destination, args.directory / 'organizer', 400 * 1024 * 1024)
    unpack(args.directory / 'organizer/data.zip', args.directory / 'data', 1500 * 1024 * 1024)
    print('Verified:', SHA256)
    print('Bags:', args.directory / 'data')


if __name__ == '__main__':
    main()
