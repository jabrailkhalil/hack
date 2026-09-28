"""Audit outer component bytes. Never promotes transport checks to training lock."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'preflight_tools'))
from precheck_components import inspect_component


def probe(teacher: Path, atlas: Path) -> dict:
    pins = json.loads((HERE / 'contracts/DEPENDENCIES.expected.json').read_text())
    records = {}
    for key, path in (('teacher', teacher), ('atlas', atlas)):
        try:
            records[key] = {'status': 'TRANSPORT_VERIFIED', **inspect_component(path, pins[key])}
        except (OSError, ValueError) as error:
            records[key] = {'status': 'MISSING_OR_INVALID', 'error': str(error),
                            'expected_sha256': pins[key]['sha256'], 'expected_bytes': pins[key]['bytes']}
    return {'stage': 'DEPENDENCY_PENDING', 'training_authorized': False,
            'native_verifiers_run': False, 'components': records,
            'next': 'Both native payload verifiers and producer-fold bridge; no fitting from this receipt'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--teacher-zip',type=Path,required=True)
    p.add_argument('--atlas-zip',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=probe(a.teacher_zip,a.atlas_zip)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as out: json.dump(result,out,indent=2);out.write('\n')
    print(json.dumps(result,indent=2))
    # This command is deliberately never a fitting authorization.
    return 3 if any(r['status']!='TRANSPORT_VERIFIED' for r in result['components'].values()) else 0

if __name__=='__main__': raise SystemExit(main())
