"""Portable H57 CLI. Serialization-only fix before either fit.

The initial F0 completed all64 bags and historical-C0 equality checks, but
JSON could not encode the NumPy int64 material-group count. Preserve that
failed attempt. This wrapper converts only scalar containers at the JSON
boundary and adds itself to the source lock. No predicate, selector,
weights, objective, optimizer, parameters or scorer is changed.
Use driver.py for every stage, not run.py directly.
"""
from pathlib import Path
import numpy as np
import run as implementation

_original_write = implementation.write
_original_sources = implementation.source_files


def native_scalars(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: native_scalars(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [native_scalars(v) for v in value]
    return value


def write(path, value):
    return _original_write(path, native_scalars(value))


def source_files():
    result = _original_sources()
    result[Path(__file__).relative_to(implementation.ROOT).as_posix()] = implementation.sha(__file__)
    return result


implementation.write = write
implementation.source_files = source_files

if __name__ == '__main__':
    implementation.main()
