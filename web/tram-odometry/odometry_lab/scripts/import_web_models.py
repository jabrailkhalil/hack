"""Import pinned, audited experiment kernels. Run from a checkout with both repos."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'odometry_lab/src/tram_lab'
records = []


def copy(repo, ref, source, target):
    commit = subprocess.check_output(['git', 'rev-parse', ref], cwd=repo).decode().strip()
    content = subprocess.check_output(['git', 'show', f'{commit}:{source}'], cwd=repo)
    path = PACKAGE / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    records.append(dict(repository='hack' if repo.name == 'hack' else 'tram-odometry',
                        commit=commit, source=source, target=target,
                        sha256=hashlib.sha256(content).hexdigest()))


for name, branch in [('common', 'concept-c'), ('concept_a', 'concept-a'),
                     ('concept_b', 'concept-b'), ('concept_c', 'concept-c'),
                     ('concept_d', 'concept-d'), ('__init__', 'concept-c')]:
    copy(ROOT, 'origin/experiments/' + branch,
         f'odometry_lab/src/tram_lab/hypotheses/{name}.py', f'hypotheses/{name}.py')
for name, branch in [('core', 'h02'), ('h01', 'h01'), ('h02', 'h02'), ('__init__', 'h02')]:
    copy(ROOT, 'origin/experiments/' + branch, f'research2/{name}.py',
         f'hypotheses/round2/{name}.py')
for name in ['fit.py', 'synthetic.py', '__init__.py', 'model.json']:
    copy(ROOT, 'origin/experiments/concept-c', 'research/' + name, 'training/' + name)
ref = 'origin/experiments/tram-h02'
for name in ['core.py', 'guarded_readout.py', 'route.py', 'timeline.py', '__init__.py']:
    copy(ROOT / 'hack', ref, 'tools/tram_port/vendor/hack/reserve_odometry/' + name,
         'vendor/hack/' + name)
for name in ['adaptive_v5', 'time_aligned_v6', 'guarded_readout_v7', 'champion_v8_extracted']:
    copy(ROOT / 'hack', ref, f'tools/tram_port/vendor/hack/config/{name}.json',
         f'vendor/hack/config/{name}.json')
(PACKAGE / 'vendor/__init__.py').write_text('')
# Verify exported ours kernels against their original branches before aliasing.
aliases = []
for record in list(records):
    target = record['target']
    if target.endswith('__init__.py'):
        continue
    if target.startswith('hypotheses/round2/'):
        upstream = 'research2/' + Path(target).name
    elif target.startswith('hypotheses/'):
        upstream = 'tram_lab/' + target
    elif target == 'training/model.json':
        upstream = 'research/model.json'
    else:
        continue
    other = subprocess.check_output(['git', 'show', f'{ref}:tools/tram_port/vendor/ours/{upstream}'], cwd=ROOT / 'hack')
    same = other.replace(b'\r\n', b'\n') == (PACKAGE / target).read_bytes().replace(b'\r\n', b'\n')
    if not same:
        raise RuntimeError('Nonidentical hack export: ' + target)
    aliases.append(dict(target=target, source='tools/tram_port/vendor/ours/' + upstream,
                        sha256=hashlib.sha256(other).hexdigest()))
document = {'files': records, 'verified_hack_aliases': aliases,
            'hack_export_commit': subprocess.check_output(['git', 'rev-parse', ref], cwd=ROOT / 'hack').decode().strip(),
            'note': 'v5-v8 are pinned profiles of the exported core, not historical binaries'}
(PACKAGE / 'model_sources.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
print(f'Imported {len(records)} sources; verified {len(aliases)} aliases.')
