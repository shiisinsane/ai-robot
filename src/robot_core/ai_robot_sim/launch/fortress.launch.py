"""在Gazebo Fortress中加载M2机器人，不启动控制器或运动命令。"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, RegisterEventHandler, TimerAction
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    description_share = get_package_share_directory('ai_robot_description')
    sim_share = get_package_share_directory('ai_robot_sim')
    ros_gz_share = get_package_share_directory('ros_gz_sim')

    world = os.path.join(sim_share, 'worlds', 'm2_empty.sdf')
    controllers = os.path.join(sim_share, 'config', 'controllers.yaml')
    model = os.path.join(description_share, 'urdf', 'ai_robot.urdf.xacro')
    robot_description = ParameterValue(
        Command([
            'xacro ', model,
            ' enable_control:=true',
            ' controller_config:=', controllers,
        ]), value_type=str)

    gz_args = [
        '-r -s ', world,
    ]

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_share, 'launch', 'gz_sim.launch.py')),
        launch_arguments={
            'gz_args': gz_args,
            'gz_version': '6',
            'on_exit_shutdown': 'true',
        }.items(),
    )

    state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        namespace='robot',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': True,
        }],
        remappings=[('tf', '/tf'), ('tf_static', '/tf_static')],
        output='screen',
    )

    clock_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='clock_bridge',
        arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
        output='screen',
    )

    spawn = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-world', 'm2_empty',
            '-name', 'ai_robot',
            '-allow_renaming', 'false',
            '-x', '0.0', '-y', '0.0', '-z', '0.12',
            '-topic', '/robot/robot_description',
        ],
        output='screen',
    )

    joint_state_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=[
            'joint_state_broadcaster',
            '--controller-manager', '/robot/controller_manager',
            '--controller-manager-timeout', '20',
        ],
        output='screen',
    )
    drive_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=[
            'diff_drive_base_controller',
            '--controller-manager', '/robot/controller_manager',
            '--controller-manager-timeout', '20',
        ],
        remappings=[
            ('/robot/diff_drive_base_controller/cmd_vel_unstamped', '/robot/cmd_vel'),
            ('/robot/diff_drive_base_controller/odom', '/robot/odom'),
        ],
        output='screen',
    )

    return LaunchDescription([
        gazebo,
        state_publisher,
        clock_bridge,
        TimerAction(period=2.0, actions=[spawn]),
        RegisterEventHandler(OnProcessExit(
            target_action=spawn,
            on_exit=[joint_state_spawner],
        )),
        RegisterEventHandler(OnProcessExit(
            target_action=joint_state_spawner,
            on_exit=[drive_spawner],
        )),
    ])
