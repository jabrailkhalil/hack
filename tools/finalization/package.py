"""Build and verify a self-contained source/evidence ZIP from tracked files.
No data downloads, fitting, execution of test measurements or GitHub writes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[2]
ALLOWED={'src','tests','tools','research','reports','submission','docs'}
ROOT_FILES={'README.md','Dockerfile.environment','requirements-dev.txt','requirements-research.txt','.gitignore','.dockerignore'}


def sha(data):return hashlib.sha256(data).hexdigest()


def verify(path):
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate archive path')
        prefix='reserve-odometry-v4/'
        for name in names:
            if not name.startswith(prefix) or '..' in Path(name).parts:raise ValueError('Unsafe archive path')
        manifest=json.loads(archive.read(prefix+'MANIFEST.json'))
        expected={prefix+p for p in manifest['files']} | {prefix+'MANIFEST.json'}
        if set(names)!=expected:raise ValueError('Unlisted/missing payload')
        for name,digest in manifest['files'].items():
            if sha(archive.read(prefix+name))!=digest:raise ValueError('Content hash mismatch: '+name)
        frozen=json.loads(archive.read(prefix+'submission/FREEZE.json'))
        for name,digest in frozen['source_sha256'].items():
            if sha(archive.read(prefix+name))!=digest:raise ValueError('Frozen source differs: '+name)
        return dict(files=len(manifest['files']),frozen_files=len(frozen['source_sha256']),sha256=sha(Path(path).read_bytes()),bytes=Path(path).stat().st_size)


def build(output):
    if output.exists():raise FileExistsError('Refusing to replace an existing release ZIP')
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    payload={}
    for name in paths:
        if not name:continue
        parts=Path(name).parts
        if parts[0] not in ALLOWED and name not in ROOT_FILES:continue
        if name.startswith(('submission/dist/','submission/checkpoints/')):continue
        if any(p in ('__pycache__','.git') for p in parts) or name.endswith(('.pyc','.db3','.zip')):continue
        path=ROOT/name
        if path.is_symlink():raise ValueError('Release does not accept symlinks: '+name)
        payload[name]=path.read_bytes()
    for required in ('submission/FREEZE.json','reports/final/test/results.json','reports/final/runtime_full.json','submission/JUDGE_GUIDE.md','submission/PLATFORM_FIELDS.md'):
        if required not in payload:raise ValueError('Missing submission evidence: '+required)
    info=dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        freeze_sha256=sha(payload['submission/FREEZE.json']),position_mode='relative_1d; optional explicitly supplied route',
        note='Source/evidence package, not a claim of map-aligned xyz accuracy or external platform submission')
    payload['BUILD_INFO.json']=(json.dumps(info,indent=2)+'\n').encode()
    manifest=dict(schema_version=1,files={name:sha(raw) for name,raw in sorted(payload.items())})
    payload['MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,raw in sorted(payload.items()):
            entry=zipfile.ZipInfo('reserve-odometry-v4/'+name,date_time=(2026,9,25,0,0,0))
            entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644 << 16
            archive.writestr(entry,raw)
    result=verify(output)
    output.with_suffix('.sha256').write_text(result['sha256']+'  '+output.name+'\n')
    output.with_suffix('.manifest.json').write_text(json.dumps(dict(**result,**info),indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'submission/dist/reserve-odometry-v4.zip')
    p.add_argument('--verify',type=Path)
    args=p.parse_args();print(json.dumps(verify(args.verify) if args.verify else build(args.output),indent=2))
