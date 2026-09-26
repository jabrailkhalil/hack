#!/usr/bin/env python3
"""Verify pinned component ZIP bytes, CRC, and manifest hash; extract separately.

Does not execute producer code, decode NPZ or authorize training. Both native
payload verifiers and the fold bridge remain mandatory. Python >= 3.10.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import zipfile

MAX_BYTES=2*1024**3
MAX_FILES=10000
ROOT=Path(__file__).resolve().parents[1]


def file_hash(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def inspect_component(path: Path, pin: dict) -> dict:
    if not path.is_file() or path.stat().st_size!=pin['bytes']:
        raise ValueError(f'ZIP missing or wrong byte length: {path}')
    actual=file_hash(path)
    if actual!=pin['sha256']:
        raise ValueError(f'ZIP SHA mismatch: {path}')
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        if len(infos)>MAX_FILES or sum(i.file_size for i in infos)>MAX_BYTES:
            raise ValueError('ZIP safety size limit exceeded')
        seen=set();manifests=[]
        files=set();dirs=set()
        for i in infos:
            q=PurePosixPath(i.filename)
            if (not i.filename or q.is_absolute() or '..' in q.parts or
                '\\' in i.filename or ':' in i.filename or '\x00' in i.filename):
                raise ValueError(f'Unsafe ZIP path: {i.filename!r}')
            name=str(q)
            if name in seen:
                raise ValueError(f'Duplicate normalized ZIP path: {name}')
            seen.add(name)
            mode=i.external_attr>>16
            if stat.S_ISLNK(mode) or i.flag_bits&1:
                raise ValueError('Symlink/encrypted member rejected')
            if stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR):
                raise ValueError('Nonregular ZIP member rejected')
            if i.is_dir(): dirs.add(name)
            else: files.add(name)
            for parent in q.parents:
                if str(parent)!='.': dirs.add(str(parent))
            if not i.is_dir() and q.name=='R5_HANDOFF.json': manifests.append(i)
        if files&dirs:
            raise ValueError('ZIP file/directory collision')
        if len(manifests)!=1:
            raise ValueError('Exactly one full R5_HANDOFF.json is required per ZIP')
        manifest=manifests[0]
        if manifest.file_size>16*1024*1024:
            raise ValueError('Manifest unexpectedly large')
        mh=hashlib.sha256(z.read(manifest)).hexdigest()
        if mh!=pin['manifest_sha256']:
            raise ValueError('Manifest SHA mismatch')
        bad=z.testzip()
        if bad:
            raise ValueError(f'ZIP CRC failure: {bad}')
    return dict(zip_sha256=actual,zip_bytes=path.stat().st_size,
                manifest_sha256=mh,manifest_member=manifest.filename,
                payload_schema_verified=False)


def extract(path: Path, dest: Path):
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f'Extraction directory must be new: {dest}')
    dest.mkdir(parents=True)
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            target=dest.joinpath(*PurePosixPath(i.filename).parts)
            if i.is_dir(): target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(i) as source,target.open('xb') as out:
                    shutil.copyfileobj(source,out)
                # Sources need not be executable for Python invocation. No special mode bits.
                target.chmod(0o755 if (i.external_attr>>16)&0o111 else 0o644)


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--teacher-zip',type=Path,required=True)
    p.add_argument('--atlas-zip',type=Path,required=True)
    p.add_argument('--extract-to',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True)
    args=p.parse_args()
    try:
        if args.extract_to.exists() or args.extract_to.is_symlink() or args.receipt.exists():
            raise FileExistsError('Use new extraction and receipt paths')
        pins=json.loads((ROOT/'contracts/DEPENDENCIES.expected.json').read_text())
        paths={'teacher':args.teacher_zip,'atlas':args.atlas_zip}
        # Inspect both completely before extracting either.
        records={k:inspect_component(v,pins[k]) for k,v in paths.items()}
        args.extract_to.mkdir(parents=True)
        for k,v in paths.items():
            dest=args.extract_to/k
            extract(v,dest)
            records[k]['manifest_path']=str(dest.joinpath(*PurePosixPath(records[k]['manifest_member']).parts).resolve())
            records[k]['component_root']=str(Path(records[k]['manifest_path']).parent)
        receipt=dict(status='TRANSPORT_VERIFIED',training_authorized=False,
                     required_next='Both native payload verifiers, then folds bridge; create new combined dependency lock',
                     components=records)
        args.receipt.parent.mkdir(parents=True,exist_ok=True)
        with args.receipt.open('x',encoding='utf-8') as f:
            json.dump(receipt,f,indent=2,ensure_ascii=False);f.write('\n')
        print(json.dumps(receipt,ensure_ascii=False))
        return 0
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile,RuntimeError) as e:
        print(f'COMPONENT_TRANSPORT_FAILED: {e}',file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
