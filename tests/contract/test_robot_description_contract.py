"""M2 URDF/Xacro描述契约测试。"""

from scripts.check_robot_description import (
    expand_description,
    validate_description,
)
from scripts.check_robot_model import load_model
from tests.conftest import REPO_ROOT


XACRO_PATH = (
    REPO_ROOT
    / "src/robot_core/ai_robot_description/urdf/ai_robot.urdf.xacro"
)
MODEL_PATH = REPO_ROOT / "config/common/robot_model.yaml"


def _validated_model():
    model = load_model(MODEL_PATH)
    root = expand_description(XACRO_PATH, MODEL_PATH)
    validate_description(root, model)
    return root


def test_description_matches_w2_model_contract():
    _validated_model()


def test_description_has_single_root_link():
    root = _validated_model()
    child_links = {
        joint.find("child").attrib["link"]
        for joint in root.findall("joint")
    }
    root_links = {
        link.attrib["name"] for link in root.findall("link")
    } - child_links

    assert root_links == {"base_link"}


def test_description_contains_no_runtime_plugins():
    root = _validated_model()
    assert root.find("gazebo") is None
    assert root.find("ros2_control") is None
