"""Check that the web lab uses the selected odometry kernel and parameters."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'web/tram-odometry/odometry_lab'


def verify():
    if not (LAB / 'pyproject.toml').is_file():
        raise ValueError('Run git submodule update --init --recursive first')
    vendor = LAB / 'src/tram_lab/vendor/hack'
    for name in ('core.py', 'timeline.py', 'guarded_readout.py'):
        local = (ROOT / 'src/reserve_odometry/reserve_odometry' / name).read_text(encoding='utf-8')
        bundled = (vendor / name).read_text(encoding='utf-8')
        if local != bundled:
            raise ValueError(f'Web kernel differs from ROS kernel: {name}')
    selected = json.loads((ROOT / 'src/reserve_odometry/config/champion_v8.json').read_text())
    bundled = json.loads((vendor / 'config/champion_v8_extracted.json').read_text())
    for key in ('config', 'readout'):
        if selected[key] != bundled[key]:
            raise ValueError(f'Web v8 parameters differ: {key}')
    return {'kernel': 'v8', 'matching_sources': 3, 'parameters_match': True,
            'scheduler': 'web receipt-clock replay; ROS adapter measured separately'}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
