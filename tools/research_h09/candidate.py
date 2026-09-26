"""Materialize the H09 algorithm patch without replacing the active v5 runtime."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
CORE = 'src/reserve_odometry/reserve_odometry/core.py'
CORE_BLOB = 'f6fc8ecd0b4e16018d814407b1944ce26ea550b0'
PATCH = ROOT / 'research/parallel/H09/core.patch'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def baseline_bytes(path, baseline_root=None):
    if baseline_root is not None:
        return (Path(baseline_root) / path).read_bytes()
    return subprocess.check_output(['git', 'show', BASELINE + ':' + path], cwd=ROOT)


def implementations(baseline_root=None):
    source = baseline_bytes(CORE, baseline_root)
    blob = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
    if blob != CORE_BLOB:
        raise ValueError('Wrong baseline core; refuse comparison')
    if source != (ROOT / CORE).read_bytes():
        raise ValueError('Active core must stay at the pinned baseline; H09 is an isolated patch')
    with tempfile.TemporaryDirectory(prefix='h09-algorithm-') as directory:
        work = Path(directory)
        destination = work / CORE
        destination.parent.mkdir(parents=True)
        destination.write_bytes(source)
        baseline_path = work / 'baseline_core.py'
        baseline_path.write_bytes(source)
        subprocess.run(['git', 'apply', '--check', str(PATCH)], cwd=work, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(['git', 'apply', str(PATCH)], cwd=work, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Package-qualified name resolves the new relative stop_history import.
        baseline = load_module('h09_frozen_core', baseline_path)
        candidate = load_module('reserve_odometry.h09_candidate', destination)
        hashes = {'baseline_core_sha256': hashlib.sha256(source).hexdigest(),
                  'candidate_core_sha256': sha(destination), 'patch_sha256': sha(PATCH),
                  'stop_history_sha256': sha(ROOT/'src/reserve_odometry/reserve_odometry/stop_history.py')}
    return baseline, candidate, hashes
