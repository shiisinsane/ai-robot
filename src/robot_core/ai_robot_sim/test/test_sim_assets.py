from pathlib import Path
import xml.etree.ElementTree as ET


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_world_is_valid_sdf_with_required_systems():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm2_empty.sdf').getroot()
    assert root.tag == 'sdf'
    world = root.find("world[@name='m2_empty']")
    assert world is not None
    filenames = {plugin.attrib['filename'] for plugin in world.findall('plugin')}
    assert 'ignition-gazebo-physics-system' in filenames
    assert 'ignition-gazebo-user-commands-system' in filenames
    assert 'ignition-gazebo-scene-broadcaster-system' in filenames


def test_world_has_static_ground_and_expected_gravity():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm2_empty.sdf').getroot()
    world = root.find("world[@name='m2_empty']")
    assert world.findtext('gravity') == '0 0 -9.80665'
    ground = world.find("model[@name='ground_plane']")
    assert ground is not None
    assert ground.findtext('static') == 'true'


def test_launch_enables_control_without_motion_publisher():
    launch_text = (PACKAGE_ROOT / 'launch' / 'fortress.launch.py').read_text()
    assert "'/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'" in launch_text
    assert "'-topic', '/robot/robot_description'" in launch_text
    assert 'enable_control:=true' in launch_text
    assert "package='controller_manager'" in launch_text
    assert 'geometry_msgs' not in launch_text
    assert "executable='cmd_vel_safety_filter.py'" in launch_text


def test_lidar_world_and_launch_are_independent_and_one_way():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm3_lidar.sdf').getroot()
    world = root.find("world[@name='m3_lidar']")
    filenames = {plugin.attrib['filename'] for plugin in world.findall('plugin')}
    assert 'ignition-gazebo-sensors-system' in filenames
    assert world.find("model[@name='front_obstacle']") is not None
    assert world.find("model[@name='left_obstacle']") is not None
    launch_text = (PACKAGE_ROOT / 'launch' / 'lidar.launch.py').read_text()
    assert 'enable_lidar:=true' in launch_text
    assert '/ai_robot_internal/lidar_scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan' in launch_text
    assert "executable='scan_adapter.py'" in launch_text
    assert "package='controller_manager'" not in launch_text


def test_camera_world_and_launch_use_internal_one_way_topics():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm3_camera.sdf').getroot()
    assert root.find("world[@name='m3_camera']/model[@name='camera_target']") is not None
    text = (PACKAGE_ROOT / 'launch' / 'camera.launch.py').read_text()
    assert 'enable_camera:=true' in text
    assert '/ai_robot_internal/camera@sensor_msgs/msg/Image[gz.msgs.Image' in text
    assert "executable='camera_adapter.py'" in text


def test_imu_world_and_launch_are_independent_and_one_way():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm3_imu.sdf').getroot()
    world = root.find("world[@name='m3_imu']")
    filenames = {plugin.attrib['filename'] for plugin in world.findall('plugin')}
    assert 'ignition-gazebo-sensors-system' in filenames
    assert 'ignition-gazebo-imu-system' in filenames
    text = (PACKAGE_ROOT / 'launch' / 'imu.launch.py').read_text()
    assert 'enable_imu:=true' in text
    assert '/ai_robot_internal/imu@sensor_msgs/msg/Imu[gz.msgs.IMU' in text
    assert "executable='imu_adapter.py'" in text
    assert "package='controller_manager'" not in text
    motion = (PACKAGE_ROOT / 'launch' / 'imu_motion.launch.py').read_text()
    assert 'enable_control:=true enable_imu:=true' in motion
    assert "executable='cmd_vel_safety_filter.py'" in motion


def test_encoder_has_independent_launch_reusing_accepted_control_chain():
    text = (PACKAGE_ROOT / 'launch' / 'encoder.launch.py').read_text()
    assert "'launch', 'fortress.launch.py'" in text
    assert 'IncludeLaunchDescription' in text


def test_m4_integrated_world_has_all_runtime_systems():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm4_integrated.sdf').getroot()
    world = root.find("world[@name='m4_integrated']")
    assert world is not None
    filenames = {plugin.attrib['filename'] for plugin in world.findall('plugin')}
    assert 'ignition-gazebo-physics-system' in filenames
    assert 'ignition-gazebo-sensors-system' in filenames
    assert 'ignition-gazebo-imu-system' in filenames
    assert world.find("model[@name='ground_plane']") is not None
    assert world.find("model[@name='integration_target']") is not None


def test_m4_integrated_launch_unifies_units_and_preserves_contract_boundaries():
    text = (PACKAGE_ROOT / 'launch' / 'integrated_bringup.launch.py').read_text()
    for option in ('enable_control:=true', 'enable_lidar:=true',
                   'enable_camera:=true', 'enable_imu:=true'):
        assert option in text
    assert 'controllers_m4.yaml' in text
    assert 'controller_odom_topic:=internal/base_odom' in text
    assert "('/robot/cmd_vel', '/robot/safety_cmd_vel')" in text
    assert 'joint_state_broadcaster' in text
    assert 'diff_drive_base_controller' in text
    assert "executable='scan_adapter.py'" in text
    assert "executable='camera_adapter.py'" in text
    assert "executable='imu_adapter.py'" in text
    assert "DeclareLaunchArgument('enable_lidar_pipeline', default_value='true')" in text
    assert "IfCondition(LaunchConfiguration('enable_lidar_pipeline'))" in text
    assert "package='image_proc'" in text
    assert "executable='rectify_node'" in text
    assert "namespace='robot/camera/color'" in text
    assert "('image', 'image_raw')" in text
    assert "('image_rect', '/robot/internal/camera/color/image_rect')" in text
    assert "executable='image_qos_adapter.py'" in text
    assert "DeclareLaunchArgument('enable_image_processing', default_value='true')" in text
    assert "executable='safety_supervisor.py'" in text
    assert "executable='joint_state_qos_adapter.py'" in text
    assert "DeclareLaunchArgument('safety_scan_topic', default_value='/robot/scan')" in text


def test_m4_controller_config_reserves_tf_for_state_estimator():
    text = (PACKAGE_ROOT / 'config' / 'controllers_m4.yaml').read_text()
    assert 'enable_odom_tf: false' in text


def test_m4_ekf_fuses_internal_odom_and_imu_with_unique_tf_authority():
    config = (PACKAGE_ROOT / 'config' / 'ekf_m4.yaml').read_text()
    assert 'odom0: /robot/internal/base_odom' in config
    assert 'imu0: /robot/imu/data' in config
    assert 'world_frame: odom' in config
    assert 'base_link_frame: base_link' in config
    assert 'publish_tf: true' in config
    launch = (PACKAGE_ROOT / 'launch' / 'integrated_bringup.launch.py').read_text()
    assert "package='robot_localization'" in launch
    assert "('odometry/filtered', '/robot/odom')" in launch
    assert 'target_action=drive_spawner' in launch
    assert 'on_exit=[state_estimator, image_processor, image_qos_adapter]' in launch


def test_m5_slam_world_launch_and_config_preserve_m4_safety_chain():
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'm5_slam.sdf').getroot()
    world = root.find("world[@name='m5_slam']")
    assert world is not None
    for model in ('north_wall', 'south_wall', 'east_wall', 'west_wall',
                  'landmark_a', 'landmark_b'):
        assert world.find(f"model[@name='{model}']") is not None

    launch = (PACKAGE_ROOT / 'launch' / 'm5_slam.launch.py').read_text()
    assert 'integrated_bringup.launch.py' in launch
    assert "executable='async_slam_toolbox_node'" in launch
    assert "namespace='robot'" in launch
    assert "('scan', '/robot/scan')" in launch
    assert "('/map', '/robot/map')" in launch
    assert "('tf', '/tf')" in launch

    params = (PACKAGE_ROOT / 'config' / 'slam_mapping.yaml').read_text()
    assert 'mode: mapping' in params
    assert 'map_frame: map' in params
    assert 'odom_frame: odom' in params
    assert 'base_frame: base_link' in params
    assert 'scan_topic: /robot/scan' in params
    assert 'transform_publish_period: 0.05' in params


def test_m5_rviz_uses_map_frame_and_public_topics():
    rviz = (PACKAGE_ROOT / 'config' / 'slam_mapping.rviz').read_text()
    assert 'Class: rviz_common/Displays\n    Name: Displays' in rviz
    assert 'Fixed Frame: map' in rviz
    assert 'Value: /robot/map' in rviz
    assert 'Value: /robot/scan' in rviz
