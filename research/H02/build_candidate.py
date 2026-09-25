"""Build the real patched core in isolation; never modify the published runtime."""
import argparse
from functools import lru_cache
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
CORE = Path('src/reserve_odometry/reserve_odometry/core.py')
PATCH = ROOT / 'research/H02/algorithm.patch'
BASE_CORE_SHA256 = '780ca4796d86b4fa4e8c8679abfb73f58f23e003d4ee644ba964ffdeac9f0bfc'
CANDIDATE_CORE_SHA256 = '07ab2334f447c4b4a0412f570cae601f40953b7994e798503ecdbcbffcacc2aa'


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def candidate_source():
    original = (ROOT / CORE).read_bytes()
    if sha_bytes(original) != BASE_CORE_SHA256:
        raise ValueError('H02 requires the exact preregistered baseline core')
    with tempfile.TemporaryDirectory(prefix='h02-core-') as directory:
        path = Path(directory) / CORE
        path.parent.mkdir(parents=True)
        path.write_bytes(original)
        subprocess.run(['git', 'apply', '--check', str(PATCH)], cwd=directory, check=True)
        subprocess.run(['git', 'apply', str(PATCH)], cwd=directory, check=True)
        source = path.read_bytes()
    if sha_bytes(source) != CANDIDATE_CORE_SHA256:
        raise ValueError('Candidate differs from the fixed H02 algorithm')
    return source


@lru_cache(maxsize=1)
def candidate_module():
    name = '_h02_candidate_core'
    module = types.ModuleType(name)
    module.__file__ = 'H02-generated-core.py'
    sys.modules[name] = module
    exec(compile(candidate_source(), module.__file__, 'exec'), module.__dict__)
    return module


def profile():
    """Read the exact v5 YAML; no fitting and no external YAML dependency."""
    values = {}
    for line in (ROOT / 'src/reserve_odometry/config/adaptive_v5.yaml').read_text().splitlines():
        line = line.strip()
        if line.startswith('model.'):
            key, value = line.split(':', 1)
            values[key[6:]] = float(value)
    if values.get('adaptation_tau_s') != 0.5:
        raise ValueError('Not the fixed adaptive_v5 baseline')
    return values


def candidate_yaml():
    text = (ROOT / 'src/reserve_odometry/config/adaptive_v5.yaml').read_text()
    return '# H02 research only, not promoted; apply algorithm.patch first.\n' + text + '    model.timing_accel_fraction: 0.5\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--params-output', type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('xb') as output:
        output.write(candidate_source())
    if args.params_output:
        with args.params_output.open('x') as output:
            output.write(candidate_yaml())
    print(CANDIDATE_CORE_SHA256, args.output)


if __name__ == '__main__':
    main()
