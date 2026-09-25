"""Apply the preregistered source change, checking the exact baseline first."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
PATH = 'src/reserve_odometry/reserve_odometry/core.py'
original = subprocess.check_output(['git', 'show', BASE + ':' + PATH], cwd=ROOT)
assert hashlib.sha1(b'blob ' + str(len(original)).encode() + b'\0' + original).hexdigest() == 'f6fc8ecd0b4e16018d814407b1944ce26ea550b0'
source = original.decode()
changes = [
    ('from typing import Optional\n', 'from typing import Optional\nfrom .numerics_h08 import predict as numerical_predict\n'),
    ('    actuator_tau_s: float = 0.35\n', '    actuator_tau_s: float = 0.35\n    numerical_prediction: float = 0.0  # H08 is opt-in; 0 preserves legacy arithmetic.\n'),
    ("        if not 0 <= self.command_deadband < 1 or self.efficiency > 1:\n",
     "        if self.numerical_prediction not in (0.0, 1.0):\n            raise ValueError('numerical_prediction must be 0 or 1')\n        if not 0 <= self.command_deadband < 1 or self.efficiency > 1:\n"),
]
legacy = '''        alpha = 1.0 - math.exp(-dt / c.actuator_tau_s)
        self.drive_a += alpha * (target - self.drive_a)
        a_model = clip(self.drive_a - self.resistance(self.v) + self.disturbance,
                       -c.max_accel_mps2, c.max_accel_mps2)
        predicted = clip(self.v + dt * a_model, -c.max_speed_mps, c.max_speed_mps)
'''
replacement = '''        if c.numerical_prediction == 1.0:
            self.drive_a, predicted = numerical_predict(
                dt, c.actuator_tau_s, self.drive_a, self.v, target,
                self.disturbance, self.resistance, c.max_accel_mps2, c.max_speed_mps)
        else:
''' + ''.join('    ' + line + '\n' for line in legacy.splitlines())
changes.append((legacy, replacement))
for before, after in changes:
    assert source.count(before) == 1, before
    source = source.replace(before, after, 1)
target = ROOT / PATH
if target.read_bytes() not in (original, source.encode()):
    raise RuntimeError('Refusing to overwrite a different core')
target.write_text(source)
profile = ROOT / 'src/reserve_odometry/config'
(profile / 'h08_exact_midpoint.yaml').write_text(
    (profile / 'adaptive_v5.yaml').read_text() + '    model.numerical_prediction: 1.0\n')
data = json.loads((profile / 'adaptive_v5.json').read_text())
data = dict(name='h08_exact_midpoint', config=data['config'] | {'numerical_prediction': 1.0},
            base_commit=BASE, hypothesis='H08', test_evaluated=False, status='research-only; not promoted')
(profile / 'h08_exact_midpoint.json').write_text(json.dumps(data, indent=2) + '\n')
print('Applied H08; adaptive_v5/default/evaluator files are unchanged')
