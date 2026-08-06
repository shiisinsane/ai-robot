"""统一启动M4底盘、雷达、相机、IMU和编码器仿真单元。"""

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
    description_share = get_package_share_directory('ai_robot_description')
    sim_share = get_package_share_directory('ai_robot_sim')
    ros_gz_share = get_package_share_directory('ros_gz_sim')
    world = os.path.join(sim_share, 'worlds', 'm4_integrated.sdf')
    controllers = os.path.join(sim_share, 'config', 'controllers_m4.yaml')
    ekf_config = os.path.join(sim_share, 'config', 'ekf_m4.yaml')
    model = os.path.join(description_share, 'urdf', 'ai_robot.urdf.xacro')
    sensor_config = os.path.join(description_share, 'config', 'sensor_model.yaml')
    with open(sensor_config, encoding='utf-8') as stream:
        imu = yaml.safe_load(stream)['imu']

    robot_description = ParameterValue(Command([
        'xacro ', model,
        ' enable_control:=true',
        ' enable_lidar:=true',
        ' enable_camera:=true',
        ' enable_imu:=true',
        ' controller_config:=', controllers,
        ' controller_odom_topic:=internal/base_odom',
    ]), value_type=str)

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_share, 'launch', 'gz_sim.launch.py')),
        launch_arguments={
            'gz_args': [
                '-r ',
                PythonExpression([
                    "'' if '", LaunchConfiguration('gui'), "' == 'true' else '-s'"
                ]),
                ' ', world,
            ],
            'gz_version': '6',
            'on_exit_shutdown': 'true',
        }.items(),
    )
    state_publisher = Node(
        package='robot_state_publisher', executable='robot_state_publisher',
        namespace='robot',
        parameters=[{'robot_description': robot_description, 'use_sim_time': True}],
        remappings=[('tf', '/tf'), ('tf_static', '/tf_static')], output='screen')
    bridges = Node(
        package='ros_gz_bridge', executable='parameter_bridge', name='sensor_bridge',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/ai_robot_internal/lidar_scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
            '/ai_robot_internal/camera@sensor_msgs/msg/Image[gz.msgs.Image',
            '/ai_robot_internal/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo',
            '/ai_robot_internal/imu@sensor_msgs/msg/Imu[gz.msgs.IMU',
        ], output='screen')
    scan_adapter = Node(
        package='ai_robot_sim', executable='scan_adapter.py', namespace='robot',
        name='lidar_driver', parameters=[{'frame_id': 'laser_link'}],
        remappings=[('scan_raw', '/ai_robot_internal/lidar_scan')],
        condition=IfCondition(LaunchConfiguration('enable_lidar_pipeline')),
        output='screen')
    camera_adapter = Node(
        package='ai_robot_sim', executable='camera_adapter.py', namespace='robot',
        name='camera_driver', parameters=[{'frame_id': 'camera_color_optical_frame'}],
        remappings=[('image_raw', '/ai_robot_internal/camera'),
                    ('camera_info_raw', '/ai_robot_internal/camera_info')], output='screen')
    imu_adapter = Node(
        package='ai_robot_sim', executable='imu_adapter.py', namespace='robot',
        name='imu_driver', parameters=[{
            'frame_id': imu['link_name'],
            'orientation_covariance': imu['covariance']['orientation'],
            'angular_velocity_covariance': imu['covariance']['angular_velocity'],
            'linear_acceleration_covariance': imu['covariance']['linear_acceleration'],
        }], remappings=[('imu_raw', '/ai_robot_internal/imu')], output='screen')
    command_filter = Node(
        package='ai_robot_sim', executable='cmd_vel_safety_filter.py', namespace='robot',
        remappings=[('/robot/cmd_vel', '/robot/safety_cmd_vel')], output='screen')
    safety_supervisor = Node(
        package='ai_robot_sim', executable='safety_supervisor.py', namespace='robot',
        remappings=[('/robot/scan', LaunchConfiguration('safety_scan_topic')),
                    ('/robot/camera/color/image_raw',
                     LaunchConfiguration('safety_camera_topic'))],
        output='screen')
    rviz = Node(
        package='rviz2', executable='rviz2',
        condition=IfCondition(LaunchConfiguration('rviz')), output='screen')
    spawn = Node(
        package='ros_gz_sim', executable='create', output='screen',
        arguments=['-world', 'm4_integrated', '-name', 'ai_robot',
                   '-allow_renaming', 'false', '-x', '0', '-y', '0', '-z', '0.12',
                   '-topic', '/robot/robot_description'])
    joint_state_spawner = Node(
        package='controller_manager', executable='spawner', output='screen',
        arguments=['joint_state_broadcaster', '--controller-manager',
                   '/robot/controller_manager', '--controller-manager-timeout', '20'])
    drive_spawner = Node(
        package='controller_manager', executable='spawner', output='screen',
        arguments=['diff_drive_base_controller', '--controller-manager',
                   '/robot/controller_manager', '--controller-manager-timeout', '20'])
    state_estimator = Node(
        package='robot_localization', executable='ekf_node', namespace='robot',
        name='state_estimator', parameters=[ekf_config, {'use_sim_time': True}],
        remappings=[('odometry/filtered', '/robot/odom'),
                    ('/diagnostics', '/robot/state_estimation/diagnostics'),
                    ('tf', '/tf'), ('tf_static', '/tf_static')], output='screen')
    image_processor = Node(
        package='image_proc', executable='rectify_node',
        namespace='robot/camera/color', name='image_rectifier',
        remappings=[('image', 'image_raw'),
                    ('image_rect', '/robot/internal/camera/color/image_rect')],
        parameters=[{'use_sim_time': True}],
        condition=IfCondition(LaunchConfiguration('enable_image_processing')),
        output='screen')
    image_qos_adapter = Node(
        package='ai_robot_sim', executable='image_qos_adapter.py',
        namespace='robot/camera/color',
        remappings=[('image_rect_internal', '/robot/internal/camera/color/image_rect')],
        condition=IfCondition(LaunchConfiguration('enable_image_processing')),
        output='screen')
    joint_state_qos_adapter = Node(
        package='ai_robot_sim', executable='joint_state_qos_adapter.py',
        namespace='robot', output='screen')

    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='false'),
        DeclareLaunchArgument('rviz', default_value='false'),
        DeclareLaunchArgument('enable_lidar_pipeline', default_value='true'),
        DeclareLaunchArgument('enable_image_processing', default_value='true'),
        DeclareLaunchArgument('safety_scan_topic', default_value='/robot/scan'),
        DeclareLaunchArgument(
            'safety_camera_topic', default_value='/robot/camera/color/image_raw'),
        gazebo, state_publisher, bridges, scan_adapter, camera_adapter, imu_adapter,
        safety_supervisor, command_filter, joint_state_qos_adapter, rviz,
        TimerAction(period=2.0, actions=[spawn]),
        RegisterEventHandler(OnProcessExit(
            target_action=spawn, on_exit=[joint_state_spawner])),
        RegisterEventHandler(OnProcessExit(
            target_action=joint_state_spawner, on_exit=[drive_spawner])),
        RegisterEventHandler(OnProcessExit(
            target_action=drive_spawner,
            on_exit=[state_estimator, image_processor, image_qos_adapter])),
    ])
