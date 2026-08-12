"""在W7基线上启动W8周期重规划、受限恢复与可取消导航。"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    sim = get_package_share_directory('ai_robot_sim')
    planning = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(sim, 'launch', 'm5_global_planning.launch.py')),
        launch_arguments={
            'gui': LaunchConfiguration('gui'),
            'map': LaunchConfiguration('map'),
        }.items())
    params = os.path.join(sim, 'config', 'nav2_local_control.yaml')
    bt_xml = os.path.join(
        sim, 'config', 'behavior_trees', 'navigate_recovery.xml')
    controller = Node(
        package='nav2_controller', executable='controller_server',
        namespace='robot', name='controller_server', parameters=[params],
        remappings=[('cmd_vel', '/robot/internal/nav_cmd_vel'),
                    ('odom', '/robot/odom')],
        output='screen')
    behavior = Node(
        package='nav2_behaviors', executable='behavior_server',
        namespace='robot', name='behavior_server', parameters=[params],
        remappings=[('cmd_vel', '/robot/internal/nav_cmd_vel'),
                    ('local_costmap_topic',
                    '/robot/local_costmap/costmap_raw')], output='screen')
    command_keepalive = Node(
        package='ai_robot_sim', executable='nav_cmd_vel_keepalive.py',
        namespace='robot', name='nav_cmd_vel_keepalive', output='screen')
    navigator = Node(
        package='nav2_bt_navigator', executable='bt_navigator',
        namespace='robot', name='bt_navigator',
        parameters=[params, {
            'default_nav_to_pose_bt_xml': bt_xml,
            'default_nav_through_poses_bt_xml': bt_xml,
        }], output='screen')
    adapter = Node(
        package='ai_robot_sim', executable='navigate_action_adapter.py',
        namespace='robot', name='navigate_action_adapter',
        parameters=[{'use_sim_time': True}], output='screen')
    lifecycle = Node(
        package='nav2_lifecycle_manager', executable='lifecycle_manager',
        namespace='robot', name='lifecycle_manager_recovery', parameters=[{
            'use_sim_time': True,
            'autostart': True,
            'node_names': ['controller_server', 'behavior_server', 'bt_navigator'],
        }], output='screen')
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='false'),
        DeclareLaunchArgument('map', description='W4保存地图YAML的绝对路径'),
        planning,
        TimerAction(period=16.0, actions=[
            command_keepalive, controller, behavior, navigator, lifecycle, adapter]),
    ])
