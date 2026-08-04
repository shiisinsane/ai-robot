"""独立启动M3 RGB相机及公共接口适配。"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _setup(context):
    desc = get_package_share_directory('ai_robot_description'); sim = get_package_share_directory('ai_robot_sim')
    ros_gz = get_package_share_directory('ros_gz_sim'); gui = context.launch_configurations['gui'].lower() == 'true'
    world = os.path.join(sim, 'worlds', 'm3_camera.sdf'); model = os.path.join(desc, 'urdf', 'ai_robot.urdf.xacro')
    robot_description = ParameterValue(Command(['xacro ', model, ' enable_camera:=true']), value_type=str)
    gazebo = IncludeLaunchDescription(PythonLaunchDescriptionSource(os.path.join(ros_gz, 'launch', 'gz_sim.launch.py')),
        launch_arguments={'gz_args': f"-r {' ' if gui else '-s '}{world}", 'gz_version': '6', 'on_exit_shutdown': 'true'}.items())
    rsp = Node(package='robot_state_publisher', executable='robot_state_publisher', namespace='robot',
        parameters=[{'robot_description': robot_description, 'use_sim_time': True}], remappings=[('tf','/tf'),('tf_static','/tf_static')])
    bridge = Node(package='ros_gz_bridge', executable='parameter_bridge', name='camera_bridge', arguments=[
        '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
        '/ai_robot_internal/camera@sensor_msgs/msg/Image[gz.msgs.Image',
        '/ai_robot_internal/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo'])
    adapter = Node(package='ai_robot_sim', executable='camera_adapter.py', namespace='robot', name='camera_driver',
        parameters=[{'frame_id':'camera_color_optical_frame'}], remappings=[
            ('image_raw','/ai_robot_internal/camera'), ('camera_info_raw','/ai_robot_internal/camera_info')])
    rviz = Node(package='rviz2', executable='rviz2', arguments=['-d',os.path.join(sim,'config','camera.rviz')],
        condition=IfCondition(LaunchConfiguration('rviz')))
    spawn = Node(package='ros_gz_sim', executable='create', arguments=['-world','m3_camera','-name','ai_robot',
        '-allow_renaming','false','-x','0','-y','0','-z','0.12','-topic','/robot/robot_description'])
    return [gazebo,rsp,bridge,adapter,rviz,TimerAction(period=2.0,actions=[spawn])]


def generate_launch_description():
    return LaunchDescription([DeclareLaunchArgument('gui',default_value='false'),
        DeclareLaunchArgument('rviz',default_value='false'),OpaqueFunction(function=_setup)])
