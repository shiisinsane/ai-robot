"""M2本体参数与M1接口、时间和TF契约的一致性测试。"""

from scripts.check_interface_contract import load_contract
from scripts.check_robot_model import load_model, validate_model
from tests.conftest import REPO_ROOT


MODEL_PATH = REPO_ROOT / "config/common/robot_model.yaml"
INTERFACE_PATH = REPO_ROOT / "config/common/interface_contract.yaml"


def test_robot_model_contract_is_valid():
    validate_model(load_model(MODEL_PATH))


def test_model_timeout_and_rate_match_interface_contract():
    model = load_model(MODEL_PATH)
    contract = load_contract(INTERFACE_PATH)
    topics = {topic["name"]: topic for topic in contract["topics"]}

    assert (
        model["control"]["cmd_vel_timeout_sec"]
        == topics["cmd_vel"]["timeout_sec"]
    )
    assert (
        model["control"]["odom_publish_rate_hz"]
        >= topics["odom"]["min_rate_hz"]
    )


def test_model_preserves_odom_to_base_link_contract():
    model = load_model(MODEL_PATH)

    assert model["control"]["odom_frame_id"] == "odom"
    assert model["control"]["base_frame_id"] == "base_link"
    assert model["frames"]["base_footprint"]["parent"] == "base_link"
