from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts.check_m5_navigation import NavigationError, validate


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def config():
    return yaml.safe_load(
        (ROOT / 'config/common/m5_navigation.yaml').read_text(encoding='utf-8'))


def test_authoritative_m5_navigation_config_passes(config):
    assert len(validate(config)) == 4


def test_rejects_simultaneous_map_tf_owners(config):
    invalid = deepcopy(config)
    invalid['tf_authority']['map_to_odom']['simultaneous_owners_forbidden'] = False
    with pytest.raises(NavigationError, match='唯一权威'):
        validate(invalid)


def test_rejects_navigation_safety_bypass(config):
    invalid = deepcopy(config)
    invalid['command_chain']['nav2_output'] = '/robot/controller_cmd_vel'
    with pytest.raises(NavigationError, match='公共安全入口'):
        validate(invalid)


def test_rejects_slam_and_amcl_in_mapping_mode(config):
    invalid = deepcopy(config)
    invalid['modes']['mapping']['disabled'] = []
    with pytest.raises(NavigationError, match='不得同时启用AMCL'):
        validate(invalid)


def test_rejects_non_stopping_scan_fault(config):
    invalid = deepcopy(config)
    invalid['fault_matrix']['scan_timeout']['response'] = 'warn_only'
    with pytest.raises(NavigationError, match='必须取消并停车'):
        validate(invalid)


def test_rejects_velocity_above_chassis_limit(config):
    invalid = deepcopy(config)
    invalid['geometry']['maximum_linear_velocity_mps'] = 0.7
    with pytest.raises(NavigationError, match='底盘限制'):
        validate(invalid)
