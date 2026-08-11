"""在W5定位基线上启动Nav2 Planner Server和全局代价地图。"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    sim = get_package_share_directory('ai_robot_sim')
    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(sim, 'launch', 'm5_localization.launch.py')),
        launch_arguments={
            'gui': LaunchConfiguration('gui'),
            'map': LaunchConfiguration('map'),
        }.items())
    params = os.path.join(sim, 'config', 'nav2_global_planning.yaml')
    planner = Node(
        package='nav2_planner', executable='planner_server', namespace='robot',
        name='planner_server', parameters=[params], output='screen')
    lifecycle = Node(
        package='nav2_lifecycle_manager', executable='lifecycle_manager',
        namespace='robot', name='lifecycle_manager_planning', parameters=[{
            'use_sim_time': True,
            'autostart': True,
            'node_names': ['planner_server'],
        }], output='screen')
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='false'),
        DeclareLaunchArgument('map', description='W4保存地图YAML的绝对路径'),
        localization,
        TimerAction(period=12.0, actions=[planner, lifecycle]),
    ])
