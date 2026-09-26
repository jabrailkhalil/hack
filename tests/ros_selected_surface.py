"""Installed release surface, not just a source-text assertion."""
from pathlib import Path
import subprocess

prefix=Path(subprocess.check_output(['ros2','pkg','prefix','reserve_odometry'],text=True).strip())
executables=subprocess.check_output(['ros2','pkg','executables','reserve_odometry'],text=True).splitlines()
assert sorted(executables)==['reserve_odometry guarded_odometry_node'], executables
share=prefix/'share/reserve_odometry'
assert sorted(p.name for p in (share/'launch').iterdir() if p.is_file())==['odometry.launch.py']
assert sorted(p.name for p in (share/'config').iterdir() if p.is_file())==['champion_v8.yaml']
print('SINGLE_SOLUTION_INSTALLED_PASS: one executable, one launch, one profile')
