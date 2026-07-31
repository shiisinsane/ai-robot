"""Python单元测试模板：验证纯逻辑，不启动ROS 2节点。"""

from copy import deepcopy

import pytest

from scripts.check_interface_contract import (
    ContractError,
    load_contract,
    validate_contract,
)
from tests.conftest import REPO_ROOT


CONTRACT_PATH = REPO_ROOT / "config/common/interface_contract.yaml"


def test_validator_accepts_current_contract():
    summary = validate_contract(load_contract(CONTRACT_PATH))
    assert len(summary) == 4


def test_validator_rejects_unknown_qos_profile():
    contract = deepcopy(load_contract(CONTRACT_PATH))
    contract["topics"][0]["qos_profile"] = "missing_profile"

    with pytest.raises(ContractError, match="未知QoS"):
        validate_contract(contract)
