"""包内Xacro展开和URDF结构测试。"""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
XACRO_FILE = PACKAGE_ROOT / "urdf/ai_robot.urdf.xacro"
MODEL_CONFIG = REPO_ROOT / "config/common/robot_model.yaml"
SENSOR_CONFIG = REPO_ROOT / "config/common/sensor_model.yaml"


def _expanded_root():
    result = subprocess.run(
        [
            "xacro",
            str(XACRO_FILE),
            f"model_config:={MODEL_CONFIG}",
            f"sensor_config:={SENSOR_CONFIG}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return ET.fromstring(result.stdout)


def _expanded_lidar_root():
    result = subprocess.run(
        [
            "xacro",
            str(XACRO_FILE),
            f"model_config:={MODEL_CONFIG}",
            f"sensor_config:={SENSOR_CONFIG}",
            "enable_lidar:=true",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return ET.fromstring(result.stdout)


def test_xacro_expands_to_expected_robot():
    root = _expanded_root()
    assert root.tag == "robot"
    assert root.attrib["name"] == "ai_robot"


def test_model_contains_required_links_and_joints():
    root = _expanded_root()
    links = {element.attrib["name"] for element in root.findall("link")}
    joints = {element.attrib["name"] for element in root.findall("joint")}

    assert links == {
        "base_link",
        "base_footprint",
        "left_wheel_link",
        "right_wheel_link",
        "front_caster_link",
        "rear_caster_link",
    }
    assert joints == {
        "base_footprint_joint",
        "left_wheel_joint",
        "right_wheel_joint",
        "front_caster_joint",
        "rear_caster_joint",
    }


def test_lidar_variant_contains_fixed_link_and_gpu_sensor():
    root = _expanded_lidar_root()
    links = {element.attrib["name"] for element in root.findall("link")}
    joints = {element.attrib["name"]: element for element in root.findall("joint")}
    assert "laser_link" in links
    assert joints["laser_joint"].attrib["type"] == "fixed"
    gazebo = root.find("gazebo[@reference='laser_link']")
    sensor = gazebo.find("sensor[@name='gpu_lidar']")
    assert sensor.attrib["type"] == "gpu_lidar"
    assert sensor.findtext("topic") == "/ai_robot_internal/lidar_scan"
    assert sensor.findtext("update_rate") == "15.0"


def test_camera_variant_contains_optical_frame_and_camera_sensor():
    result = subprocess.run([
        "xacro", str(XACRO_FILE), f"model_config:={MODEL_CONFIG}",
        f"sensor_config:={SENSOR_CONFIG}", "enable_camera:=true",
    ], check=True, capture_output=True, text=True)
    root = ET.fromstring(result.stdout)
    links = {item.attrib["name"] for item in root.findall("link")}
    assert {"camera_link", "camera_color_optical_frame"}.issubset(links)
    sensor = root.find("gazebo[@reference='camera_link']/sensor[@name='color_camera']")
    assert sensor is not None
    assert sensor.findtext("topic") == "/ai_robot_internal/camera"


def test_imu_variant_contains_fixed_link_and_imu_sensor():
    result = subprocess.run([
        "xacro", str(XACRO_FILE), f"model_config:={MODEL_CONFIG}",
        f"sensor_config:={SENSOR_CONFIG}", "enable_imu:=true",
    ], check=True, capture_output=True, text=True)
    root = ET.fromstring(result.stdout)
    links = {item.attrib["name"] for item in root.findall("link")}
    assert "imu_link" in links
    joint = root.find("joint[@name='imu_joint']")
    assert joint is not None and joint.attrib["type"] == "fixed"
    sensor = root.find("gazebo[@reference='imu_link']/sensor[@name='imu_sensor']")
    assert sensor is not None and sensor.attrib["type"] == "imu"
    assert sensor.findtext("topic") == "/ai_robot_internal/imu"
    assert sensor.findtext("update_rate") == "50.0"
