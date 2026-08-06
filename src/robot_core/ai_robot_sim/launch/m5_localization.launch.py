"""加载静态地图并在M4整机仿真中启动AMCL定位。"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    sim = get_package_share_directory('ai_robot_sim')
    bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(sim, 'launch', 'integrated_bringup.launch.py')),
        launch_arguments={'gui': LaunchConfiguration('gui'), 'rviz': 'false',
                          'world': os.path.join(sim, 'worlds', 'm5_slam.sdf'),
                          'world_name': 'm5_slam'}.items())
    map_server = Node(
        package='nav2_map_server', executable='map_server', namespace='robot',
        name='map_server', parameters=[{'use_sim_time': True,
                                       'yaml_filename': LaunchConfiguration('map')}],
        remappings=[('/map', '/robot/map'), ('/map_metadata', '/robot/map_metadata')],
        output='screen')
    amcl = Node(
        package='nav2_amcl', executable='amcl', namespace='robot', name='amcl',
        parameters=[os.path.join(sim, 'config', 'amcl_localization.yaml')],
        remappings=[('amcl_pose', '/robot/pose'), ('initialpose', '/robot/initialpose'),
                    ('tf', '/tf'), ('tf_static', '/tf_static')], output='screen')
    lifecycle = Node(
        package='nav2_lifecycle_manager', executable='lifecycle_manager', namespace='robot',
        name='lifecycle_manager_localization', parameters=[{
            'use_sim_time': True, 'autostart': True,
            'node_names': ['map_server', 'amcl']}], output='screen')
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='false'),
        DeclareLaunchArgument('map', description='W4保存地图YAML的绝对路径'),
        bringup, TimerAction(period=8.0, actions=[map_server, amcl, lifecycle])])
