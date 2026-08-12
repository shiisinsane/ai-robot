"""在W6规划链上启动W7局部控制和静态导航。"""

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
    bt_xml = os.path.join(sim, 'config', 'behavior_trees', 'navigate_static.xml')
    controller = Node(
        package='nav2_controller', executable='controller_server',
        namespace='robot', name='controller_server', parameters=[params],
        remappings=[('cmd_vel', '/robot/cmd_vel'), ('odom', '/robot/odom')],
        output='screen')
    navigator = Node(
        package='nav2_bt_navigator', executable='bt_navigator',
        namespace='robot', name='bt_navigator',
        parameters=[params, {
            'default_nav_to_pose_bt_xml': bt_xml,
            # Humble会预加载多目标树；W7不提供多目标公共入口。
            'default_nav_through_poses_bt_xml': bt_xml,
        }],
        output='screen')
    action_adapter = Node(
        package='ai_robot_sim', executable='navigate_action_adapter.py',
        namespace='robot', name='navigate_action_adapter',
        parameters=[{'use_sim_time': True}], output='screen')
    lifecycle = Node(
        package='nav2_lifecycle_manager', executable='lifecycle_manager',
        namespace='robot', name='lifecycle_manager_control', parameters=[{
            'use_sim_time': True,
            'autostart': True,
            'node_names': ['controller_server', 'bt_navigator'],
        }], output='screen')
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='false'),
        DeclareLaunchArgument('map', description='W4保存地图YAML的绝对路径'),
        planning,
        TimerAction(period=16.0, actions=[controller, navigator, lifecycle,
                                          action_adapter]),
    ])
