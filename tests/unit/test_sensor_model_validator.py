"""M3传感器参数验证器单元测试。"""

from copy import deepcopy

import pytest

from scripts.check_sensor_model import SensorContractError, load_yaml, validate_sensor_model
from tests.conftest import REPO_ROOT


SENSOR_PATH = REPO_ROOT / "config/common/sensor_model.yaml"
CONTRACT_PATH = REPO_ROOT / "config/common/interface_contract.yaml"
ROBOT_PATH = REPO_ROOT / "config/common/robot_model.yaml"


def _inputs():
    return load_yaml(SENSOR_PATH), load_yaml(CONTRACT_PATH), load_yaml(ROBOT_PATH)


def test_validator_accepts_current_sensor_model():
    assert len(validate_sensor_model(*_inputs())) == 4


def test_validator_rejects_camera_rate_below_contract():
    sensors, contract, robot = _inputs()
    sensors = deepcopy(sensors)
    sensors["camera"]["update_rate_hz"] = 10.0
    with pytest.raises(SensorContractError, match="频率低于"):
        validate_sensor_model(sensors, contract, robot)


def test_validator_rejects_wrong_optical_rotation():
    sensors, contract, robot = _inputs()
    sensors = deepcopy(sensors)
    sensors["camera"]["optical_frame"]["rpy"] = [0.0, 0.0, 0.0]
    with pytest.raises(SensorContractError, match="REP-103"):
        validate_sensor_model(sensors, contract, robot)


def test_validator_rejects_imu_covariance_mismatch():
    sensors, contract, robot = _inputs()
    sensors = deepcopy(sensors)
    sensors["imu"]["covariance"]["linear_acceleration"][0] = 0.04
    with pytest.raises(SensorContractError, match="对角值错误"):
        validate_sensor_model(sensors, contract, robot)
