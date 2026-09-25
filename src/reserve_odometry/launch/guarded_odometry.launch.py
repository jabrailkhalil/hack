"""Launch the installed optional module without changing the default entrypoint."""
from pathlib import Path
import sys
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    config = str(Path(get_package_share_directory('reserve_odometry')) / 'config' / 'guarded_readout_v7.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('params_file', default_value=config),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        ExecuteProcess(cmd=[sys.executable, '-m', 'reserve_odometry.guarded_node',
                            '--ros-args', '--params-file', LaunchConfiguration('params_file'),
                            '-p', ['use_sim_time:=', LaunchConfiguration('use_sim_time')]],
                       output='screen'),
    ])
