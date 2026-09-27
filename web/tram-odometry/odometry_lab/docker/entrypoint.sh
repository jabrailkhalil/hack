#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
if [[ ! -f /opt/ros_ws/install/setup.bash ]]; then
  if [[ ! -d /dataset/tram_vehicle_msgs ]]; then
    echo 'Mount the dataset read-only at /dataset (including tram_vehicle_msgs).' >&2
    exit 2
  fi
  python3 /opt/lab/docker/prepare_workspace.py
  cd /opt/ros_ws
  colcon build --executor sequential
  if [[ -d /artifacts ]]; then
    cp -a log /artifacts/colcon-log
  fi
fi
source /opt/ros_ws/install/setup.bash
cd /opt/lab
if [[ "$1" == smoke ]]; then
  exec python3 /opt/lab/docker/smoke.py
elif [[ "$1" == test ]]; then
  exec python3 -m pytest /opt/lab/tests -q -m 'not dataset'
elif [[ "$1" == node ]]; then
  shift
  exec ros2 run tram_lab_ros estimator --ros-args -p use_sim_time:=true "$@"
fi
exec "$@"
