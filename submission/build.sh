#!/usr/bin/env bash
# Offline build in a separate prefix: never run stale executables from old install/.
set -eo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source /opt/ros/humble/setup.bash
export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-2}"
export MAKEFLAGS="${MAKEFLAGS:--j2}"
colcon --log-base log_main build --base-paths src --build-base build_main --install-base install_main --executor sequential
source install_main/setup.bash
PYTHONPATH=src/reserve_odometry python3 -m unittest discover -s tests -v
python3 tests/ros_selected_surface.py
python3 tests/ros_calibrated_smoke.py
python3 tests/ros_fault_smoke.py
python3 tests/ros_low_speed_lock_smoke.py
python3 tests/cdr_roundtrip.py
