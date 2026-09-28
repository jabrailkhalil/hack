"""Format already measured JSON coefficients as ROS double parameters.

Post-hoc artifact conversion only: no fitting, replay, or numerical change.
Original train/A.yaml and B.yaml are kept unchanged as execution evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def render(source: Path, template: Path, output: Path) -> dict:
    item = json.loads(source.read_text())
    config = item['config']
    if output.exists():
        raise FileExistsError(output)
    seen = set()
    lines = ['# H16: REJECTED research calibration; post-hoc ROS double serialization only.']
    for line in template.read_text().splitlines():
        key, sep, value = line.strip().partition(':')
        if sep and key.startswith('model.'):
            field = key[6:]
            x = float(config[field])
            if x != config[field]:
                raise ValueError('Numerical value changed: ' + field)
            line = '    ' + key + ': ' + repr(x)
            seen.add(field)
        lines.append(line)
    if seen != set(config):
        raise ValueError('Template/config fields differ')
    text = '\n'.join(lines) + '\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
    parsed = {k.strip()[6:]: float(v.strip()) for line in lines
              if (k := line.partition(':')[0]).strip().startswith('model.')
              for v in [line.partition(':')[2]]}
    assert parsed == config
    return dict(source_json_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                yaml_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                all_model_values_equal=True,model_fields=len(seen),
                installed_ros_test_executed=False)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--template', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(render(a.source, a.template, a.output), indent=2))

if __name__ == '__main__':
    main()
