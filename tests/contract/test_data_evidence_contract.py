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
G1_FREEZE = REPO_ROOT / "config/common/g1_entity_interface_freeze.yaml"
G1_RESOURCE_BUDGET = REPO_ROOT / "config/common/g1_entity_resource_budget.yaml"
G1_SAFETY_PLAN = REPO_ROOT / "config/common/g1_entity_safety_plan.yaml"
INTERFACE_CONTRACT = REPO_ROOT / "config/common/interface_contract.yaml"


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


def test_g1_entity_freeze_covers_public_contract_without_vendor_names():
    freeze = _load_yaml(G1_FREEZE)
    contract = _load_yaml(INTERFACE_CONTRACT)
    frozen = freeze["public_contract"]
    frozen_names = {
        *frozen["topics"]["required"], *frozen["topics"]["conditional"],
        *frozen["services"]["required"], *frozen["actions"]["required"],
    }
    contract_names = {
        entry["name"]
        for group in ("topics", "services", "actions")
        for entry in contract[group]
    }
    assert freeze["source_interface_version"] == contract["interface_version"]
    assert frozen_names == contract_names
    assert all(not name.startswith("/") for name in frozen_names)
    assert freeze["rules"]["forbid_vendor_or_mode_in_public_names"] is True


def test_g1_entity_freeze_preserves_safety_time_and_tf_boundaries():
    freeze = _load_yaml(G1_FREEZE)
    assert freeze["time"]["entity"]["use_sim_time"] is False
    assert freeze["time"]["watchdog_clock"] == "steady"
    assert freeze["tf"]["authorities"]["map_to_odom"]["exclusive"] is True
    assert freeze["tf"]["authorities"]["odom_to_base_link"]["exclusive"] is True
    chain = freeze["command_and_safety_chain"]
    assert chain["application_input"] == "/robot/cmd_vel"
    assert chain["controller_input"] == "/robot/controller_cmd_vel"
    assert chain["emergency_stop"]["independent_from_ros_required"] is True
    assert freeze["rules"]["direct_controller_access_forbidden"] is True


def test_g1_resource_budget_separates_safety_and_reserves_capacity():
    budget = _load_yaml(G1_RESOURCE_BUDGET)
    assert budget["topology"]["safety"]["ros_independent"] is True
    assert budget["topology"]["motion_control"]["mcu_local_closed_loop"] is True
    for bus in ("ethernet", "usb3", "can", "uart"):
        utilization = budget["capacity_rules"][bus][
            "sustained_utilization_max_fraction"]
        assert 0.0 < utilization <= 0.60
    assert budget["power_rules"]["branch_fusing_required"] is True
    assert budget["power_rules"]["emergency_stop_removes_motor_torque"] is True
    assert budget["boundaries"]["no_procurement_decision"] is True


def test_g1_resource_budget_keeps_unknown_entity_inputs_explicit():
    budget = _load_yaml(G1_RESOURCE_BUDGET)
    pending = set(budget["pending_hard_inputs"])
    assert {
        "total_budget", "robot_mass_and_payload",
        "battery_voltage_capacity_and_runtime", "host_compute_model_and_ports",
        "enclosure_dimensions_and_mounting_space",
    } <= pending
    assert budget["compute_acceptance"]["ros_distro"] == "humble"
    assert budget["installation_rules"][
        "measured_extrinsics_required_before_entity_navigation"] is True


def test_g1_entity_safety_plan_has_progressive_gates_and_no_auto_restart():
    plan = _load_yaml(G1_SAFETY_PLAN)
    gates = plan["gates"]
    assert [gate["id"] for gate in gates] == ["G0", "G1", "G2", "G3", "G4", "G5"]
    assert gates[0]["motion_allowed"] is False
    assert gates[1]["motion_allowed"] is False
    assert gates[2]["name"] == "wheels_off_ground"
    assert plan["principles"]["two_person_rule_for_first_motion"] is True
    assert plan["emergency_stop"]["reset_motion_inhibited"] is True
    assert plan["emergency_stop"]["reset_requires_manual_action"] is True


def test_g1_entity_safety_plan_preserves_watchdogs_and_safe_evidence():
    plan = _load_yaml(G1_SAFETY_PLAN)
    software = plan["software_safety"]
    assert software["command_timeout_sec"] == 0.2
    assert software["scan_timeout_sec"] == 0.5
    assert software["driver_loss_action"] == "latch_stop_and_abort_task"
    assert plan["evidence"]["velocity_command_topics_forbidden"] is True
    assert plan["evidence"]["manifest_and_sha256_required"] is True
    assert plan["boundaries"]["no_entity_motion_in_g1"] is True
