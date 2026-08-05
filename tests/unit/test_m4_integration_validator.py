from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts.check_m4_integration import IntegrationError, validate


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def config():
    return yaml.safe_load(
        (ROOT / 'config/common/m4_integration.yaml').read_text(encoding='utf-8'))


def test_authoritative_m4_integration_config_passes(config):
    assert len(validate(config)) == 4


def test_rejects_duplicate_odom_tf_authority(config):
    invalid = deepcopy(config)
    invalid['state_estimation']['tf_authority']['diff_drive_publish_tf'] = True
    with pytest.raises(IntegrationError, match='唯一发布'):
        validate(invalid)


def test_rejects_public_command_bypass(config):
    invalid = deepcopy(config)
    invalid['command_chain']['public_owner'] = 'diff_drive_base_controller'
    with pytest.raises(IntegrationError, match='安全监督'):
        validate(invalid)


def test_rejects_non_stopping_scan_timeout(config):
    invalid = deepcopy(config)
    invalid['safety']['monitors']['scan']['severity'] = 'warn'
    with pytest.raises(IntegrationError, match='关键运动输入'):
        validate(invalid)


def test_rejects_image_frame_change(config):
    invalid = deepcopy(config)
    invalid['image_processing']['preserve_frame'] = 'camera_link'
    with pytest.raises(IntegrationError, match='光学Frame'):
        validate(invalid)
