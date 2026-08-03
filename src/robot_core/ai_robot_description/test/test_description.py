"""包内Xacro展开和URDF结构测试。"""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
XACRO_FILE = PACKAGE_ROOT / "urdf/ai_robot.urdf.xacro"
MODEL_CONFIG = REPO_ROOT / "config/common/robot_model.yaml"


def _expanded_root():
    result = subprocess.run(
        [
            "xacro",
            str(XACRO_FILE),
            f"model_config:={MODEL_CONFIG}",
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
