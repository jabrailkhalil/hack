#!/usr/bin/env bash
set -eo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source /opt/ros/humble/setup.bash
source install/setup.bash
if [[ "${1:-}" == "--clock" ]]; then
  shift
  exec ros2 run reserve_odometry odometry_node --ros-args \
    --params-file "$ROOT/src/reserve_odometry/config/default.yaml" \
    -p use_sim_time:=true -p clock_mode:=ros_clock "$@"
else
  exec ros2 launch reserve_odometry odometry.launch.py \
    params_file:="$ROOT/src/reserve_odometry/config/default.yaml" "$@"
fi
