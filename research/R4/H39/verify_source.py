#!/usr/bin/env python3
"""Verify the complete R4 baseline ZIP without Git/network; optionally extract safely.

No file is executed. A matching tree authenticates snapshot bytes/modes against
an already trusted expected tree, not the commit history or an author signature.
Python >= 3.10; standard library only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

BASELINE_COMMIT = 'e3b0c9c039d2953fbfcda51231263d38ef9f1024'
EXPECTED_TREE = 'eae49a504bc59b5c9b408445150bef32e111956f'
EXPECTED_COUNT = 301
SENTINEL = 'src/reserve_odometry/reserve_odometry/core.py'
MAX_BYTES = 256 * 1024 * 1024


def git_object(kind: str, value: bytes) -> bytes:
    return hashlib.sha1(f'{kind} {len(value)}\0'.encode('ascii') + value).digest()


def tree_hash(files: dict[str, tuple[str, bytes]]) -> str:
    root: dict = {}
    for path, (mode, value) in files.items():
        parts = path.split('/')
        node = root
        for part in parts[:-1]:
            child = node.setdefault(part, {})
            if not isinstance(child, dict):
                raise ValueError(f'File/directory collision: {path}')
            node = child
        if parts[-1] in node:
            raise ValueError(f'Duplicate/colliding path: {path}')
        node[parts[-1]] = (mode, git_object('blob', value))
    def digest(node: dict) -> bytes:
        entries = []
        for name, value in node.items():
            encoded = name.encode('utf-8')
            if isinstance(value, dict):
                mode, sha, key = '40000', digest(value), encoded + b'/'
            else:
                mode, sha = value
                key = encoded
            entries.append((key, mode.encode('ascii') + b' ' + encoded + b'\0' + sha))
        return git_object('tree', b''.join(v for _, v in sorted(entries)))
    return digest(root).hex()


def inspect_zip(path: Path) -> tuple[dict, dict[str, tuple[str, bytes]]]:
    raw_hash = hashlib.sha256()
    with path.open('rb') as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b''):
            raw_hash.update(block)
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = set()
        for info in infos:
            p = PurePosixPath(info.filename)
            if (not info.filename or '\\' in info.filename or p.is_absolute()
                or '..' in p.parts or ':' in (p.parts[0] if p.parts else '')
                or '\0' in info.filename):
                raise ValueError(f'Unsafe member: {info.filename!r}')
            if info.filename in names:
                raise ValueError(f'Duplicate ZIP member: {info.filename!r}')
            names.add(info.filename)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f'Symlink member forbidden: {info.filename}')
            if info.flag_bits & 1:
                raise ValueError('Encrypted members are not accepted')
        if sum(x.file_size for x in infos) > MAX_BYTES:
            raise ValueError('Uncompressed size limit exceeded')
        roots = {x.filename[:-len(SENTINEL)] for x in infos
                 if x.filename.endswith(SENTINEL)
                 and not x.filename.startswith('__MACOSX/')}
        if len(roots) != 1:
            raise ValueError(f'Expected one source root, found {len(roots)}')
        prefix = roots.pop()
        files: dict[str, tuple[str, bytes]] = {}
        ignored = []
        for info in infos:
            if info.is_dir():
                continue
            if info.filename.startswith('__MACOSX/'):
                ignored.append(info.filename)
                continue
            if not info.filename.startswith(prefix):
                raise ValueError(f'Unexpected file outside source root: {info.filename}')
            relative = info.filename[len(prefix):]
            # Verify exact original path spelling; do not silently normalize.
            if not relative or str(PurePosixPath(relative)) != relative:
                raise ValueError(f'Noncanonical path: {relative!r}')
            mode = info.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise ValueError(f'Unsupported file type: {info.filename}')
            git_mode = '100755' if mode & 0o111 else '100644'
            value = archive.read(info)  # also verifies each member CRC
            if relative in files:
                raise ValueError(f'Duplicate source file: {relative}')
            files[relative] = (git_mode, value)
    actual_tree = tree_hash(files)
    report = {
        'source_status': 'VERIFIED' if actual_tree == EXPECTED_TREE and len(files) == EXPECTED_COUNT else 'MISMATCH',
        'baseline_commit_binding': BASELINE_COMMIT,
        'expected_git_tree': EXPECTED_TREE,
        'actual_git_tree': actual_tree,
        'file_count': len(files),
        'expected_file_count': EXPECTED_COUNT,
        'zip_name': path.name,
        'zip_bytes': path.stat().st_size,
        'zip_sha256': raw_hash.hexdigest(),
        'source_root': prefix,
        'ignored_macos_metadata_files': len(ignored),
        'git_history_present': any(p.startswith('.git/') or p == '.git' for p in files),
        'dataset_db3_present': any(p.endswith('.db3') for p in files),
        'r3_reports_present': any(p.startswith('reports/research_R3/') for p in files),
        'verification_scope': 'All source paths, original bytes, and executable bits; not remote history or dataset',
        'files': [dict(path=p, size=len(b), mode=m, sha256=hashlib.sha256(b).hexdigest(),
                       git_blob=git_object('blob', b).hex()) for p, (m, b) in sorted(files.items())]
    }
    return report, files


def extract_verified(destination: Path, files: dict[str, tuple[str, bytes]]) -> None:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f'Extraction destination must be new: {destination}')
    destination.mkdir(parents=True, exist_ok=False)
    for relative, (mode, data) in files.items():
        target = destination.joinpath(*relative.split('/'))
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as fh:
            fh.write(data)
        os.chmod(target, 0o755 if mode == '100755' else 0o644)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip', type=Path)
    parser.add_argument('--report', type=Path, help='New JSON file; existing evidence is never overwritten')
    parser.add_argument('--extract', type=Path, help='New destination; extraction occurs only after a match')
    args = parser.parse_args()
    try:
        report, files = inspect_zip(args.zip)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open('x', encoding='utf-8') as fh:
                json.dump(report, fh, indent=2, ensure_ascii=False)
                fh.write('\n')
        print(json.dumps({k: v for k, v in report.items() if k != 'files'}, indent=2, ensure_ascii=False))
        if report['source_status'] != 'VERIFIED':
            return 2
        if args.extract:
            extract_verified(args.extract, files)
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        print(f'SOURCE_CHECK_ERROR: {exc}', file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
