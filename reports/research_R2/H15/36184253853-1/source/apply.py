"""Apply only H15 patch; retain an independent canonical v7 for equivalence."""
from pathlib import Path
import hashlib, json, subprocess, shutil
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
m=json.loads((HERE/'baseline_manifest.json').read_text())
core=ROOT/'src/reserve_odometry/reserve_odometry/core.py'
if hashlib.sha256(core.read_bytes()).hexdigest()!=m['sha256'][str(core.relative_to(ROOT))]:
    raise ValueError('Apply requires clean fixed baseline core, not an already applied patch')
for p,h in m['sha256'].items():
    if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h:raise ValueError('Baseline file changed: '+p)
canonical=HERE/'_canonical';canonical.mkdir(exist_ok=True)
(canonical/'__init__.py').write_text('')
for name in ('core.py','guarded_readout.py'):
    shutil.copyfile(core.parent/name,canonical/name)
subprocess.run(['git','apply','--check',str(HERE/'algorithm.patch')],cwd=ROOT,check=True)
subprocess.run(['git','apply',str(HERE/'algorithm.patch')],cwd=ROOT,check=True)
assert hashlib.sha256(core.read_bytes()).hexdigest()==m['patched_core_sha256']
print('H15 patch applied; canonical v7 retained; no historical pins rewritten')
