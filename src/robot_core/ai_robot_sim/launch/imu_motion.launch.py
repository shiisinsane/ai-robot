"""以M2安全控制链驱动原地旋转，仅用于M3-W5 IMU动态符号测试。"""
import os
import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, RegisterEventHandler, TimerAction
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    desc=get_package_share_directory('ai_robot_description'); sim=get_package_share_directory('ai_robot_sim')
    ros_gz=get_package_share_directory('ros_gz_sim'); controllers=os.path.join(sim,'config','controllers.yaml')
    model=os.path.join(desc,'urdf','ai_robot.urdf.xacro'); sensor_config=os.path.join(desc,'config','sensor_model.yaml')
    with open(sensor_config,encoding='utf-8') as stream: imu=yaml.safe_load(stream)['imu']
    description=ParameterValue(Command(['xacro ',model,' enable_control:=true enable_imu:=true controller_config:=',controllers]),value_type=str)
    world=os.path.join(sim,'worlds','m3_imu.sdf')
    gz_args=PythonExpression(["'-r ' if '",LaunchConfiguration('gui'),"' == 'true' else '-r -s '"," + '",world,"'"])
    gazebo=IncludeLaunchDescription(PythonLaunchDescriptionSource(os.path.join(ros_gz,'launch','gz_sim.launch.py')),
        launch_arguments={'gz_args':gz_args,'gz_version':'6','on_exit_shutdown':'true'}.items())
    rsp=Node(package='robot_state_publisher',executable='robot_state_publisher',namespace='robot',
        parameters=[{'robot_description':description,'use_sim_time':True}],remappings=[('tf','/tf'),('tf_static','/tf_static')])
    bridge=Node(package='ros_gz_bridge',executable='parameter_bridge',name='imu_motion_bridge',arguments=[
        '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock','/ai_robot_internal/imu@sensor_msgs/msg/Imu[gz.msgs.IMU'])
    adapter=Node(package='ai_robot_sim',executable='imu_adapter.py',namespace='robot',parameters=[{
        'frame_id':imu['link_name'],'orientation_covariance':imu['covariance']['orientation'],
        'angular_velocity_covariance':imu['covariance']['angular_velocity'],
        'linear_acceleration_covariance':imu['covariance']['linear_acceleration']}],remappings=[('imu_raw','/ai_robot_internal/imu')])
    safety=Node(package='ai_robot_sim',executable='cmd_vel_safety_filter.py',namespace='robot')
    rviz=Node(package='rviz2',executable='rviz2',arguments=['-d',os.path.join(sim,'config','imu.rviz')],
        condition=IfCondition(LaunchConfiguration('rviz')))
    spawn=Node(package='ros_gz_sim',executable='create',arguments=['-world','m3_imu','-name','ai_robot','-allow_renaming','false',
        '-x','0','-y','0','-z','0.12','-topic','/robot/robot_description'])
    joints=Node(package='controller_manager',executable='spawner',arguments=['joint_state_broadcaster','--controller-manager','/robot/controller_manager','--controller-manager-timeout','20'])
    drive=Node(package='controller_manager',executable='spawner',arguments=['diff_drive_base_controller','--controller-manager','/robot/controller_manager','--controller-manager-timeout','20'])
    return LaunchDescription([DeclareLaunchArgument('gui',default_value='false'),
        DeclareLaunchArgument('rviz',default_value='false'),gazebo,rsp,bridge,adapter,safety,rviz,TimerAction(period=2.0,actions=[spawn]),
        RegisterEventHandler(OnProcessExit(target_action=spawn,on_exit=[joints])),
        RegisterEventHandler(OnProcessExit(target_action=joints,on_exit=[drive]))])
