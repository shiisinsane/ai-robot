"""契约测试模板：检查公共接口、QoS、时间和TF基线。"""

from scripts.check_interface_contract import load_contract, validate_contract
from tests.conftest import REPO_ROOT


CONTRACT_PATH = REPO_ROOT / "config/common/interface_contract.yaml"


def test_machine_readable_contract_is_valid():
    validate_contract(load_contract(CONTRACT_PATH))


def test_safety_topics_fail_closed():
    contract = load_contract(CONTRACT_PATH)
    topics = {topic["name"]: topic for topic in contract["topics"]}

    assert topics["cmd_vel"]["timeout_action"] == "stop"
    assert topics["cmd_vel"]["timeout_sec"] == 0.2
    assert (
        topics["safety/stop_active"]["timeout_action"]
        == "assume_stop_active"
    )
    assert topics["safety/stop_active"]["timeout_sec"] == 0.3


def test_public_interfaces_do_not_encode_runtime_mode():
    contract = load_contract(CONTRACT_PATH)
    entries = contract["topics"] + contract["services"] + contract["actions"]

    forbidden_tokens = {"sim", "real", "gazebo", "fortress"}
    for entry in entries:
        segments = set(entry["name"].split("/"))
        assert segments.isdisjoint(forbidden_tokens)
