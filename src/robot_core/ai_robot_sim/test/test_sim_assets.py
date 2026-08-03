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
