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
