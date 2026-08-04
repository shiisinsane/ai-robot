"""独立启动M3激光雷达单元及单向ROS 2桥接。"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _launch_setup(context):
    description_share = get_package_share_directory('ai_robot_description')
    sim_share = get_package_share_directory('ai_robot_sim')
    ros_gz_share = get_package_share_directory('ros_gz_sim')
    gui = context.launch_configurations['gui'].lower() == 'true'
    world = os.path.join(sim_share, 'worlds', 'm3_lidar.sdf')
    model = os.path.join(description_share, 'urdf', 'ai_robot.urdf.xacro')
    robot_description = ParameterValue(
        Command(['xacro ', model, ' enable_lidar:=true']), value_type=str
    )
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(ros_gz_share, 'launch', 'gz_sim.launch.py')),
        launch_arguments={
            'gz_args': f"-r {' ' if gui else '-s '}{world}",
            'gz_version': '6',
            'on_exit_shutdown': 'true',
        }.items(),
    )
    state_publisher = Node(
        package='robot_state_publisher', executable='robot_state_publisher', namespace='robot',
        parameters=[{'robot_description': robot_description, 'use_sim_time': True}],
        remappings=[('tf', '/tf'), ('tf_static', '/tf_static')], output='screen',
    )
    bridges = Node(
        package='ros_gz_bridge', executable='parameter_bridge', name='lidar_bridge',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/ai_robot_internal/lidar_scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
        ], output='screen',
    )
    scan_adapter = Node(
        package='ai_robot_sim', executable='scan_adapter.py',
        namespace='robot', name='lidar_driver',
        parameters=[{'frame_id': 'laser_link'}],
        remappings=[('scan_raw', '/ai_robot_internal/lidar_scan')],
        output='screen',
    )
    rviz = Node(
        package='rviz2', executable='rviz2',
        arguments=['-d', os.path.join(sim_share, 'config', 'lidar.rviz')],
        condition=IfCondition(LaunchConfiguration('rviz')),
        output='screen',
    )
    spawn = Node(
        package='ros_gz_sim', executable='create',
        arguments=[
            '-world', 'm3_lidar', '-name', 'ai_robot', '-allow_renaming', 'false',
            '-x', '0.0', '-y', '0.0', '-z', '0.12', '-topic', '/robot/robot_description',
        ], output='screen',
    )
    return [gazebo, state_publisher, bridges, scan_adapter, rviz, TimerAction(period=2.0, actions=[spawn])]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='false'),
        DeclareLaunchArgument('rviz', default_value='false'),
        OpaqueFunction(function=_launch_setup),
    ])
