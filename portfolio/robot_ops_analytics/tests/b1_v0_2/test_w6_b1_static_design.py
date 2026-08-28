from pathlib import Path
import hashlib
import json

import yaml

from portfolio.robot_ops_analytics.pipelines.b1_v0_2.audit_b1_static_design import audit
from portfolio.robot_ops_analytics.pipelines.b1_v0_2.generate_w6_b1_pilot_plan import generate
from portfolio.robot_ops_analytics.pipelines.b1_v0_2.generate_w6_b1_formal_plan import generate as generate_formal


ROOT = Path(__file__).parents[2]


def _config():
    return yaml.safe_load((ROOT / "config/w6_b1_long_route_draft_v0.2.yaml").read_text(encoding="utf-8"))


def test_b1_draft_passes_conservative_geometry_gate():
    result = audit(_config())
    assert result["status"] == "pass"
    profiles = {item["profile"]: item for item in result["profiles"]}
    assert profiles["medium"]["start_and_target_outside_inflation"] is True
    assert profiles["medium"]["largest_detour_corridor_m"] >= 1.0


def test_b1_gate_rejects_obstacle_covering_endpoint():
    config = _config()
    medium = next(item for item in config["obstacle_profiles"] if item["id"] == "medium")
    medium["position"]["x_m"] = config["route"]["start_pose"]["x_m"]
    result = audit(config)
    profiles = {item["profile"]: item for item in result["profiles"]}
    assert result["status"] == "fail"
    assert profiles["medium"]["start_and_target_outside_inflation"] is False


def test_b1_pilot_plan_is_three_qualification_only_tasks():
    rows = generate(_config())
    assert [row["obstacle_profile"] for row in rows] == ["none", "low", "medium"]
    assert all(row["qualification_ready"] for row in rows)
    assert all(not row["environment_ready"] for row in rows)
    assert all(row["start_x"] == -2.0 and row["target_x"] == 2.0 for row in rows)


def test_b1_formal_plan_is_balanced_and_authorized():
    config = yaml.safe_load((ROOT / "config/w6_b1_preregistration_v0.2.yaml").read_text(encoding="utf-8"))
    rows = generate_formal(config)
    assert len(rows) == 45
    assert all(sum(row["obstacle_profile"] == profile for row in rows) == 15 for profile in ("none", "low", "medium"))
    assert all(row["environment_ready"] and not row["qualification_ready"] for row in rows)
    assert all(row["repetition"] == row["validation_block"] for row in rows)
    for block in range(1, 16):
        assert {row["obstacle_profile"] for row in rows if row["validation_block"] == block} == {"none", "low", "medium"}


def test_frozen_b1_formal_plan_matches_generator_and_preregistered_sha():
    config = yaml.safe_load(
        (ROOT / "config/w6_b1_preregistration_v0.2.yaml").read_text(encoding="utf-8"))
    frozen_path = ROOT / "plans/b1_v0_2/w6_b1_formal_plan_v0.2.jsonl"
    payload = frozen_path.read_text(encoding="utf-8")
    frozen = [json.loads(line) for line in payload.splitlines() if line.strip()]
    assert frozen == generate_formal(config)
    assert hashlib.sha256(payload.encode()).hexdigest() == config["assignment"][
        "frozen_plan_sha256"]
