"""Read-only component presence check, NEVER a successful dependency lock.

A correct ZIP hash is only a transport prerequisite. It cannot establish the
producer's native payload schemas or folds bridge. No optimizer is invoked.
"""
import argparse
import hashlib
import json
from pathlib import Path

PINS = {
    'teacher': ('R5_H42_teacher_component.zip', 28190115,
        '2ee08edb32343350bf6ae6202836644de4fb309640f2d140a1eb9d5791af28b8',
        '5c8129133758bbb715f2e170122b976f95d0240c18daa731472d910f0bf274d0'),
    'atlas': ('R5_H43_atlas_handoff.zip', 1076521,
        '6a759f4bafe4ece014e9dd4f25b201549e317f2ca9db7b47b6c15d4443d9b011',
        '73d3269f012f25f4c46787369bdb85fc218fbf149d29cd60c63eb8f20687bd5c'),
}


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def check(teacher_zip: Path, atlas_zip: Path):
    rows = {}
    for kind, path in (('teacher', teacher_zip), ('atlas', atlas_zip)):
        name, size, digest, manifest = PINS[kind]
        row = dict(expected_name=name, expected_bytes=size, expected_sha256=digest,
                   expected_manifest_sha256=manifest, supplied_path=str(path), status='MISSING')
        if path.is_file():
            row['actual_bytes'] = path.stat().st_size
            row['actual_sha256'] = sha256(path)
            row['status'] = ('ZIP_HASH_ONLY' if row['actual_bytes'] == size
                             and row['actual_sha256'] == digest else 'MISMATCH')
        rows[kind] = row
    state = 'DEPENDENCY_PENDING' if any(r['status'] == 'MISSING' for r in rows.values()) else (
        'DEPENDENCY_MISMATCH' if any(r['status'] == 'MISMATCH' for r in rows.values())
        else 'NATIVE_VERIFICATION_REQUIRED')
    return dict(hypothesis_id='R5-H47', stage=state, scientific_verdict='NOT_EVALUATED',
                is_dependency_lock=False, training_authorized=False, components=rows,
                native_payload_verification='NOT_RUN', folds_bridge='NOT_RUN',
                combined_lock_created=False,
                required_next='Wave2 transport precheck, both native verifiers, actual-folds bridge, new combined lock')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--teacher-zip', type=Path, required=True)
    p.add_argument('--atlas-zip', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.name == 'DEPENDENCIES.lock.json':
        p.error('A presence receipt must not be named DEPENDENCIES.lock.json')
    result = check(args.teacher_zip, args.atlas_zip)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False); f.write('\n')
    print(json.dumps(result, ensure_ascii=False))
    return 3  # Deliberately never success/training authorization at this stage.

if __name__ == '__main__':
    raise SystemExit(main())
