"""Build independent pristine package from a fully verified user baseline ZIP.

This is preparation, not a Git ancestry assertion. Never runs the measurement
loader and never changes canonical configs or evaluator files. Apply in an
isolated research checkout. Requires local git apply, but no network or .git.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
from verify_source import inspect_zip,extract_verified

ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'research/R4_H34'


def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline-zip',type=Path,required=True);a=p.parse_args()
    receipt,files=inspect_zip(a.baseline_zip)
    if receipt['source_status']!='VERIFIED':raise ValueError('Full baseline tree mismatch')
    saved=D/'SOURCE_RECEIPT.json'
    if not saved.exists():saved.write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n')
    else:
        old=json.loads(saved.read_text())
        if old['files']!=receipt['files']:raise ValueError('Existing receipt disagrees with snapshot')
    dest=D/'pristine_package';dest.mkdir(exist_ok=True)
    prefix='src/reserve_odometry/reserve_odometry/'
    for path,(_,data) in files.items():
        if path.startswith(prefix):
            target=dest/path[len(prefix):];target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists() and target.read_bytes()!=data:raise ValueError('Existing pristine package changed')
            if not target.exists():target.write_bytes(data)
    core=ROOT/(prefix+'core.py');readout=ROOT/(prefix+'guarded_readout.py')
    pins=json.loads((D/'candidate_manifest.json').read_text())
    if all(hashlib.sha256(f.read_bytes()).hexdigest()==pins[str(f.relative_to(ROOT))] for f in (core,readout)):
        print('Verified already applied H34 hooks, no second application');return
    for f in (core,readout):
        if f.read_bytes()!=files[str(f.relative_to(ROOT))][1]:raise ValueError('Runtime is neither pristine nor exactly patched')
    subprocess.run(['git','apply','--check',str(D/'hooks.patch')],cwd=ROOT,check=True)
    subprocess.run(['git','apply',str(D/'hooks.patch')],cwd=ROOT,check=True)
    for f in (core,readout):
        if hashlib.sha256(f.read_bytes()).hexdigest()!=pins[str(f.relative_to(ROOT))]:raise ValueError('Patched source hash mismatch')
    print('Independent baseline package and isolated hooks ready')

if __name__=='__main__':main()
