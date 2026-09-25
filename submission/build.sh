#!/usr/bin/env bash
# Dependencies must already be installed. No apt, pip, rosdep or downloads here.
set -eo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source /opt/ros/humble/setup.bash
export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-2}"
export MAKEFLAGS="${MAKEFLAGS:--j2}"
colcon build --base-paths src --executor sequential
source install/setup.bash
PYTHONPATH=src/reserve_odometry python3 -m unittest discover -s tests -v
python3 tests/ros_smoke.py
python3 tests/ros_calibrated_smoke.py
python3 tests/ros_fault_smoke.py
python3 tests/cdr_roundtrip.py
