"""Run the unchanged installed-node fault assertions with H04's explicit profile.

Only the params-file launch argument is substituted. No thresholds, clocks,
inputs, or assertions from tests/ros_fault_smoke.py are changed.
"""
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests'))
import ros_fault_smoke

original_popen = subprocess.Popen

def candidate_launch(args, *positional, **keywords):
    args = list(args)
    if args[:4] != ['ros2', 'run', 'reserve_odometry', 'odometry_node']:
        raise AssertionError('Unexpected subprocess in pinned ROS fault test')
    index = args.index('--params-file') + 1
    if Path(args[index]) != ROOT/'src/reserve_odometry/config/default.yaml':
        raise AssertionError('The pinned ROS fault launcher changed')
    args[index] = str(ROOT/'research/H04/config.yaml')
    print('H04_FAULT_PARAMS', args[index], flush=True)
    return original_popen(args, *positional, **keywords)

if __name__ == '__main__':
    with patch.object(subprocess, 'Popen', candidate_launch):
        ros_fault_smoke.main()
