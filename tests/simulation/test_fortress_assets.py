from pathlib import Path
import xml.etree.ElementTree as ET

import yaml


ROOT = Path(__file__).resolve().parents[2]
SIM_PACKAGE = ROOT / 'src' / 'robot_core' / 'ai_robot_sim'


def test_sim_package_declares_runtime_dependencies():
    package = ET.parse(SIM_PACKAGE / 'package.xml').getroot()
    dependencies = {node.text for node in package.findall('exec_depend')}
    assert {'ai_robot_description', 'ros_gz_sim', 'ros_gz_bridge'} <= dependencies


def test_install_rule_contains_launch_and_worlds():
    cmake = (SIM_PACKAGE / 'CMakeLists.txt').read_text()
    assert 'install(DIRECTORY config launch worlds' in cmake
    assert 'scripts/cmd_vel_safety_filter.py' in cmake


def test_w4_launch_is_headless_and_uses_sim_time():
    launch_text = (SIM_PACKAGE / 'launch' / 'fortress.launch.py').read_text()
    assert "'-r -s '" in launch_text
    assert "'use_sim_time': True" in launch_text
    assert "'-z', '0.12'" in launch_text


def test_w5_controller_order_and_public_interfaces():
    launch_text = (SIM_PACKAGE / 'launch' / 'fortress.launch.py').read_text()
    filter_text = (
        SIM_PACKAGE / 'scripts' / 'cmd_vel_safety_filter.py'
    ).read_text()
    control_text = (
        ROOT / 'src' / 'robot_core' / 'ai_robot_description' /
        'urdf' / 'macros' / 'control.xacro'
    ).read_text()
    assert launch_text.index('joint_state_spawner =') < launch_text.index('drive_spawner =')
    assert "'/robot/controller_manager'" in launch_text
    assert "'/robot/cmd_vel'" in filter_text
    assert 'cmd_vel_unstamped:=controller_cmd_vel' in control_text
    assert "'/robot/controller_cmd_vel'" in filter_text
    assert 'diff_drive_base_controller/odom:=odom' in control_text


def test_w5_controller_parameters_match_model_baseline():
    text = (SIM_PACKAGE / 'config' / 'controllers.yaml').read_text()
    for expected in ('wheel_separation: 0.34', 'wheel_radius: 0.075',
                     'cmd_vel_timeout: 0.2', 'update_rate: 100',
                     'tf_frame_prefix_enable: false'):
        assert expected in text


def test_w8_regression_entry_covers_motion_safety_and_minimal_bag():
    regression = (ROOT / 'scripts' / 'run_m2_regression.py').read_text()
    assert "'check_m2_motion.py'" in regression
    assert "'check_m2_w7_safety.py'" in regression
    for topic in ('/clock', '/robot/cmd_vel', '/robot/odom',
                  '/robot/joint_states', '/tf', '/tf_static'):
        assert topic in regression
    assert '/m2_w8/replay/cmd_vel' not in regression


def test_w8_rosbag_qos_matches_runtime_contract():
    qos_path = ROOT / 'config' / 'common' / 'm2_rosbag_qos.yaml'
    qos = yaml.safe_load(qos_path.read_text())
    assert qos['/robot/cmd_vel']['reliability'] == 'reliable'
    assert qos['/robot/odom']['reliability'] == 'reliable'
    assert qos['/tf']['durability'] == 'volatile'
    assert qos['/tf_static']['durability'] == 'transient_local'


def test_m3_w6_encoder_check_covers_rate_direction_and_odometry():
    text = (ROOT / 'scripts' / 'check_m3_encoder.py').read_text()
    for expected in ('MIN_RATE_HZ', 'left_wheel_joint', 'right_wheel_joint',
                     'WHEEL_RADIUS', 'WHEEL_SEPARATION', '/robot/odom',
                     '/robot/joint_states'):
        assert expected in text
    assert 'encoder_distance' in text
    assert 'encoder_yaw' in text


def test_m3_w7_regression_covers_all_sensors_bags_and_hashes():
    text = (ROOT / 'scripts' / 'run_m3_regression.py').read_text()
    for expected in ("'lidar'", "'camera'", "'imu'", "'encoder'",
                     'check_m2_motion.py', 'check_m2_w7_safety.py',
                     "'ros2', 'bag', 'record'", "'ros2', 'bag', 'play'",
                     'sha256', 'manifest.yaml'):
        assert expected in text
    assert 'ROS_DOMAIN_ID' in text
    assert 'IGN_PARTITION' in text
