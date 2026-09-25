"""Read the immutable v4 artifact, not the changing operational default.

Historical evidence is checked against its exact evaluated source bytes. Active
runtime/profile integrity has its own PROMOTION manifest and tests. No network
or raw measurements are used by these helpers.
"""
import hashlib
from pathlib import Path, PurePosixPath
import zipfile
ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'submission/dist/reserve-odometry-v4.zip'
EXPECTED_SHA256 = '1c51975f63c1cc6eecc4473e10441d72b77916d78e5be26c094ed1ff263fc139'
PREFIX = 'reserve-odometry-v4/'


def verified_archive():
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise ValueError('Historical v4 archive changed')
    return zipfile.ZipFile(ARCHIVE)


def read_v4(relative_path):
    path = PurePosixPath(relative_path)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Invalid archived path')
    with verified_archive() as archive:
        return archive.read(PREFIX + path.as_posix())


def extract_v4(destination):
    destination = Path(destination).resolve()
    with verified_archive() as archive:
        for entry in archive.infolist():
            target = (destination / entry.filename).resolve()
            if destination not in target.parents:
                raise ValueError('Unsafe archived path')
        archive.extractall(destination)
    return destination / PREFIX.rstrip('/')
