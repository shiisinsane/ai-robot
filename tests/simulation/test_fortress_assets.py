from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
SIM_PACKAGE = ROOT / 'src' / 'robot_core' / 'ai_robot_sim'


def test_sim_package_declares_runtime_dependencies():
    package = ET.parse(SIM_PACKAGE / 'package.xml').getroot()
    dependencies = {node.text for node in package.findall('exec_depend')}
    assert {'ai_robot_description', 'ros_gz_sim', 'ros_gz_bridge'} <= dependencies


def test_install_rule_contains_launch_and_worlds():
    cmake = (SIM_PACKAGE / 'CMakeLists.txt').read_text()
    assert 'install(DIRECTORY config launch worlds' in cmake


def test_w4_launch_is_headless_and_uses_sim_time():
    launch_text = (SIM_PACKAGE / 'launch' / 'fortress.launch.py').read_text()
    assert "'-r -s '" in launch_text
    assert "'use_sim_time': True" in launch_text
    assert "'-z', '0.12'" in launch_text


def test_w5_controller_order_and_public_interfaces():
    launch_text = (SIM_PACKAGE / 'launch' / 'fortress.launch.py').read_text()
    assert launch_text.index('joint_state_spawner =') < launch_text.index('drive_spawner =')
    assert "'/robot/controller_manager'" in launch_text
    assert "'/robot/cmd_vel'" in launch_text
    assert "'/robot/odom'" in launch_text


def test_w5_controller_parameters_match_model_baseline():
    text = (SIM_PACKAGE / 'config' / 'controllers.yaml').read_text()
    for expected in ('wheel_separation: 0.34', 'wheel_radius: 0.075',
                     'cmd_vel_timeout: 0.2', 'update_rate: 100',
                     'tf_frame_prefix_enable: false'):
        assert expected in text
