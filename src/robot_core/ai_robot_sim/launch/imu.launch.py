"""独立启动M3 IMU单元及公共接口适配。"""
import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _setup(context):
    description = get_package_share_directory('ai_robot_description')
    simulation = get_package_share_directory('ai_robot_sim')
    ros_gz = get_package_share_directory('ros_gz_sim')
    gui = context.launch_configurations['gui'].lower() == 'true'
    world_name = 'm3_imu'
    world = os.path.join(simulation, 'worlds', 'm3_imu.sdf')
    model = os.path.join(description, 'urdf', 'ai_robot.urdf.xacro')
    sensor_config = os.path.join(description, 'config', 'sensor_model.yaml')
    with open(sensor_config, encoding='utf-8') as stream:
        imu = yaml.safe_load(stream)['imu']
    robot_description = ParameterValue(Command(['xacro ', model, ' enable_imu:=true']), value_type=str)
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(ros_gz, 'launch', 'gz_sim.launch.py')),
        launch_arguments={'gz_args': f"-r {' ' if gui else '-s '}{world}", 'gz_version': '6', 'on_exit_shutdown': 'true'}.items())
    state_publisher = Node(package='robot_state_publisher', executable='robot_state_publisher', namespace='robot',
        parameters=[{'robot_description': robot_description, 'use_sim_time': True}], remappings=[('tf','/tf'),('tf_static','/tf_static')])
    bridge = Node(package='ros_gz_bridge', executable='parameter_bridge', name='imu_bridge', arguments=[
        '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
        '/ai_robot_internal/imu@sensor_msgs/msg/Imu[gz.msgs.IMU'])
    adapter = Node(package='ai_robot_sim', executable='imu_adapter.py', namespace='robot', name='imu_driver',
        parameters=[{'frame_id': imu['link_name'],
                     'orientation_covariance': imu['covariance']['orientation'],
                     'angular_velocity_covariance': imu['covariance']['angular_velocity'],
                     'linear_acceleration_covariance': imu['covariance']['linear_acceleration']}],
        remappings=[('imu_raw','/ai_robot_internal/imu')])
    rviz = Node(package='rviz2', executable='rviz2', arguments=['-d',os.path.join(simulation,'config','imu.rviz')],
        condition=IfCondition(LaunchConfiguration('rviz')))
    spawn = Node(package='ros_gz_sim', executable='create', arguments=['-world',world_name,'-name','ai_robot',
        '-allow_renaming','false','-x','0','-y','0','-z','0.12','-topic','/robot/robot_description'])
    return [gazebo,state_publisher,bridge,adapter,rviz,TimerAction(period=2.0,actions=[spawn])]


def generate_launch_description():
    return LaunchDescription([DeclareLaunchArgument('gui',default_value='false'),
        DeclareLaunchArgument('rviz',default_value='false'),OpaqueFunction(function=_setup)])
