from pathlib import Path
import json

import pytest
import yaml

from portfolio.robot_ops_analytics.pipelines.b2_v0_3.generate_w7_b2_qualification_plan import generate
from portfolio.robot_ops_analytics.pipelines.b2_v0_3.write_pilot_obstacle_config import build
from portfolio.robot_ops_analytics.pipelines.b2_v0_3.run_w7_b2_diagnostic import (
    DEFAULT_PLAN, build_run, select_task)
from portfolio.robot_ops_analytics.pipelines.b2_v0_3.validate_w7_b2_runtime import (
    validate as validate_runtime)


ROOT = Path(__file__).resolve().parents[2]


def test_b2_qualification_plan_has_15_isolated_gui_tasks():
    design = yaml.safe_load((ROOT / "config/w7_b2_design_draft_v0.1.yaml").read_text())
    qualification = yaml.safe_load((ROOT / "config/w7_b2_qualification_v0.1.yaml").read_text())
    rows = generate(design, qualification)
    assert len(rows) == 15
    assert [row["ros_domain_id"] for row in rows] == list(range(140, 155))
    assert len({row["gazebo_partition"] for row in rows}) == 15
    assert len({(row["route_id"], row["obstacle_profile"]) for row in rows}) == 15
    assert all(row["requires_gui"] and row["qualification_ready"] for row in rows)
    assert all(not row["environment_ready"] and not row["formal_dataset_admission"] for row in rows)


def test_all_qualification_pilots_passed_without_formal_collection_authorization():
    qualification = yaml.safe_load(
        (ROOT / "config/w7_b2_qualification_v0.1.yaml").read_text())
    assert qualification["status"] == "qualification_complete_waiting_preregistration_review"
    assert qualification["pilot_execution_authorized"] is False
    assert qualification["task_authorization_scope"] == "pilot_15_only_user_manually_starts_gui"
    assert qualification["authorized_task_id"] == "b2-pilot-horizontal_offset-medium"
    assert qualification["authorized_task_sequence"] == 15
    assert qualification["pilot_07_pause_reason"] == "start_pose_overlaps_fixed_landmark_b"
    assert qualification["pilot_07_repair_scope"] == (
        "repaired_route_attempt_002_only_user_manually_starts_gui")
    assert qualification["next_pending_task_id"] is None
    assert qualification["qualification_result"] == "15_of_15_passed"
    assert qualification["formal_collection_authorized"] is False


def test_frozen_qualification_plan_matches_generator():
    design = yaml.safe_load((ROOT / "config/w7_b2_design_draft_v0.1.yaml").read_text())
    qualification = yaml.safe_load(
        (ROOT / "config/w7_b2_qualification_v0.1.yaml").read_text())
    frozen_path = ROOT / "plans/b2_v0_3/w7_b2_qualification_plan_v0.1.jsonl"
    frozen = [json.loads(line) for line in frozen_path.read_text().splitlines() if line.strip()]
    assert frozen == generate(design, qualification)


def test_each_pilot_obstacle_config_matches_plan_position():
    design = yaml.safe_load((ROOT / "config/w7_b2_design_draft_v0.1.yaml").read_text())
    qualification = yaml.safe_load((ROOT / "config/w7_b2_qualification_v0.1.yaml").read_text())
    for row in generate(design, qualification):
        profile = build(row)["obstacle_profiles"][0]
        assert profile["id"] == row["obstacle_profile"]
        assert profile["route_id"] == row["route_id"]
        assert profile["x_m"] == row["obstacle_position"]["x_m"]
        assert profile["y_m"] == row["obstacle_position"]["y_m"]


def test_diagnostic_launcher_derives_all_task_parameters_from_plan():
    task = select_task(DEFAULT_PLAN, "b2-pilot-horizontal_center-low")
    _, obstacle_path, domain_id, partition, command = build_run(
        task, DEFAULT_PLAN, "manual_diagnostic_test", 158)
    assert command[command.index("--initial-pose") + 1:command.index("--initial-pose") + 4] == [
        "-2.0", "0.0", "0.0"]
    assert command[command.index("--environment-profile") + 1] == task["environment_profile"]
    assert command[command.index("--obstacle-profile") + 1] == "low"
    assert command[command.index("--task-id") + 1] == task["task_id"]
    assert str(obstacle_path) in command
    assert domain_id == 158
    assert partition == "roa_b2_manual_diagnostic_test"


def test_runtime_gate_accepts_derived_values_and_rejects_wrong_spawn(tmp_path):
    task = select_task(DEFAULT_PLAN, "b2-pilot-horizontal_center-low")
    obstacle = tmp_path / "obstacle.yaml"
    obstacle.write_text(yaml.safe_dump(build(task), sort_keys=False), encoding="utf-8")
    args = (DEFAULT_PLAN, task["task_id"], task["environment_profile"],
            task["obstacle_profile"], task["initial_perturbation"])
    assert validate_runtime(*args, (-2.0, 0.0, 0.0), obstacle) == task
    with pytest.raises(ValueError, match="initial-pose"):
        validate_runtime(*args, (0.0, 0.0, 0.0), obstacle)


def test_b2_runtime_schema_files_are_valid_json():
    schema_root = ROOT / "schemas/versions/roa-b2-qualification-v0.1"
    for name in ("qualification_plan.schema.json", "obstacle_runtime.schema.json"):
        schema = json.loads((schema_root / name).read_text(encoding="utf-8"))
        assert schema["$schema"].endswith("2020-12/schema")
        assert schema["type"] == "object"


def test_preacceptance_freezes_time_after_lifecycle_query():
    source = (ROOT / "pipelines/common/run_experiment.py").read_text(encoding="utf-8")
    lifecycle = source.index(
        "navigation_nodes_active = self._navigation_nodes_active()")
    coherent_time = source.index(
        "now_sim = self._wait_coherent_snapshot_time(freshness_sec)")
    snapshot = source.index("snapshot = build_preacceptance_snapshot(")
    assert lifecycle < coherent_time < snapshot
    assert "navigation_nodes_active=navigation_nodes_active" in source
