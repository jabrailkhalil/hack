#!/usr/bin/env bash
set -eo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source /opt/ros/humble/setup.bash
if [[ ! -f install_main/setup.bash ]]; then
  echo "Run bash submission/build.sh first (selected install_main prefix)." >&2
  exit 2
fi
source install_main/setup.bash
if [[ "${1:-}" == "--clock" ]]; then
  shift
  exec ros2 run reserve_odometry guarded_odometry_node --ros-args \
    --params-file "$(ros2 pkg prefix reserve_odometry)/share/reserve_odometry/config/champion_v8.yaml" \
    -p use_sim_time:=true -p clock_mode:=ros_clock "$@"
else
  exec ros2 launch reserve_odometry odometry.launch.py "$@"
fi
