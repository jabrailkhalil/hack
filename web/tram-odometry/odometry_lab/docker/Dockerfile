FROM ros:humble-ros-base@sha256:1813d3c85d7f96ff7d3012d865204583255740182db5d0065f8f8cd029a83138
SHELL ["/bin/bash", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip python3-colcon-common-extensions build-essential cmake \
    ros-humble-rosbag2 ros-humble-rosbag2-storage-default-plugins \
    ros-humble-nav-msgs ros-humble-diagnostic-msgs ros-humble-rosgraph-msgs \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/lab
COPY pyproject.toml requirements.txt /opt/lab/
RUN python3 -m pip install --no-cache-dir 'pip==25.0.1' \
    && python3 -m pip install --no-cache-dir -r requirements.txt
COPY src /opt/lab/src
RUN python3 -m pip install --no-build-isolation --no-deps . \
    && python3 -c "import tram_lab; from importlib.metadata import version; assert version('tram-odometry-lab') == '0.1.0'"
COPY ros2 /opt/ros_ws/src
COPY tests /opt/lab/tests
COPY configs /opt/lab/configs
COPY docker /opt/lab/docker
ENV PYTHONUNBUFFERED=1 ROS_DOMAIN_ID=97 ROS_LOCALHOST_ONLY=1 MPLCONFIGDIR=/tmp/matplotlib
ENTRYPOINT ["/bin/bash", "/opt/lab/docker/entrypoint.sh"]
CMD ["smoke"]
