"""M2机器人本体参数验证器单元测试。"""

from copy import deepcopy

import pytest

from scripts.check_robot_model import (
    ModelContractError,
    load_model,
    validate_model,
)
from tests.conftest import REPO_ROOT


MODEL_PATH = REPO_ROOT / "config/common/robot_model.yaml"


def test_validator_accepts_current_robot_model():
    summary = validate_model(load_model(MODEL_PATH))
    assert len(summary) == 4


def test_validator_rejects_asymmetric_wheels():
    model = deepcopy(load_model(MODEL_PATH))
    model["drive"]["wheels"]["right"]["xyz"][1] = -0.16

    with pytest.raises(ModelContractError, match="对称"):
        validate_model(model)


def test_validator_rejects_relaxed_command_timeout():
    model = deepcopy(load_model(MODEL_PATH))
    model["control"]["cmd_vel_timeout_sec"] = 0.5

    with pytest.raises(ModelContractError, match="0.2 s"):
        validate_model(model)
