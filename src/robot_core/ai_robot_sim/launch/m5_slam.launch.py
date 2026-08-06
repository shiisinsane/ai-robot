"""在已验收M4整机链上启动M5异步二维SLAM。"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    sim_share = get_package_share_directory('ai_robot_sim')
    world = os.path.join(sim_share, 'worlds', 'm5_slam.sdf')
    slam_params = os.path.join(sim_share, 'config', 'slam_mapping.yaml')
    rviz_config = os.path.join(sim_share, 'config', 'slam_mapping.rviz')

    m4_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(sim_share, 'launch', 'integrated_bringup.launch.py')),
        launch_arguments={
            'gui': LaunchConfiguration('gui'),
            'rviz': 'false',
            'world': world,
            'world_name': 'm5_slam',
        }.items(),
    )
    slam = Node(
        package='slam_toolbox', executable='async_slam_toolbox_node',
        namespace='robot', name='slam_toolbox',
        parameters=[slam_params, {'use_sim_time': True}],
        remappings=[('scan', '/robot/scan'), ('/map', '/robot/map'),
                    ('/map_metadata', '/robot/map_metadata'),
                    ('tf', '/tf'), ('tf_static', '/tf_static')],
        output='screen')
    rviz = Node(
        package='rviz2', executable='rviz2', arguments=['-d', rviz_config],
        condition=IfCondition(LaunchConfiguration('rviz')), output='screen')

    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='false'),
        DeclareLaunchArgument('rviz', default_value='false'),
        m4_bringup,
        TimerAction(period=8.0, actions=[slam]),
        rviz,
    ])
