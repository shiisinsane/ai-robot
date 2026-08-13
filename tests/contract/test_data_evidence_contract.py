"""W7数据与证据配置测试。"""

from copy import deepcopy

import pytest
import yaml

from scripts.check_evidence_manifest import ManifestError, validate_manifest
from scripts.check_rosbag import _profile_topics
from tests.conftest import REPO_ROOT


RECORDING_CONFIG = (
    REPO_ROOT / "config/common/rosbag_recording.yaml"
)
MANIFEST_TEMPLATE = (
    REPO_ROOT / "test_data/templates/evidence_manifest.yaml"
)
M6_QOS = REPO_ROOT / "config/common/m6_rosbag_qos.yaml"
M6_RUNNER = REPO_ROOT / "scripts/run_m6_regression.py"


def _load_yaml(path):
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def test_recording_profiles_are_explicit_and_inherit_core_topics():
    config = _load_yaml(RECORDING_CONFIG)
    core_required, _ = _profile_topics(config, "core")
    navigation_required, _ = _profile_topics(config, "navigation")

    assert config["rules"]["forbid_record_all"] is True
    assert "/robot/odom" in core_required
    assert core_required < navigation_required
    assert "/robot/scan" in navigation_required


def test_evidence_manifest_template_is_valid():
    summary = validate_manifest(_load_yaml(MANIFEST_TEMPLATE))
    assert len(summary) == 3


def test_evidence_manifest_rejects_missing_commit():
    manifest = deepcopy(_load_yaml(MANIFEST_TEMPLATE))
    manifest["source"]["git_commit"] = ""

    with pytest.raises(ManifestError, match="git_commit"):
        validate_manifest(manifest)


def test_m6_evidence_records_task_feedback_without_velocity_commands():
    qos = _load_yaml(M6_QOS)
    runner = M6_RUNNER.read_text(encoding="utf-8")
    assert "/robot/task/execute/_action/feedback" in runner
    assert "/robot/task/execute/_action/status" in runner
    assert "/robot/cmd_vel" not in runner
    assert qos["/robot/safety/stop_active"]["durability"] == "transient_local"
