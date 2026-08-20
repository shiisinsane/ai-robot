import ast
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def test_w3_config_keeps_public_action_and_required_topics():
    config = yaml.safe_load((ROOT / "config/w3_collection.yaml").read_text(encoding="utf-8"))
    assert config["action_name"] == "task/execute"
    assert set(config["required_telemetry_topics"]) == {"odom", "pose", "scan", "safety"}
    assert config["ready"]["require_clock_advancing"] is True
    assert config["ready"]["require_safety_stop_inactive"] is True


def test_collector_has_no_control_publisher():
    tree = ast.parse((ROOT / "collector/ros_collector.py").read_text(encoding="utf-8"))
    publisher_calls = [node for node in ast.walk(tree) if isinstance(node, ast.Attribute)
                       and node.attr == "create_publisher"]
    assert publisher_calls == []
    text = (ROOT / "collector/ros_collector.py").read_text(encoding="utf-8")
    assert "cmd_vel" not in text
    assert "def _context(" not in text
    assert "def _uint8(" in text


def test_orchestrator_only_publishes_internal_context():
    text = (ROOT / "orchestrator/run_experiment.py").read_text(encoding="utf-8")
    assert 'ActionClient(self, ExecuteRobotTask, "task/execute")' in text
    assert 'String, "analytics/task_context"' in text
    assert "self.context =" not in text
    assert "cmd_vel" not in text
    assert "_wait_ready" in text
    assert "_wait_collector" in text
    assert 'count_subscribers("analytics/task_context")' in text
    assert "not self._safety_stop" in text


def test_synthetic_fixture_is_valid_jsonl_and_explicitly_synthetic():
    rows = [json.loads(line) for line in (ROOT / "samples/w3_synthetic_fixture.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 3
    assert all(row["schema_version"] == "roa-schema-v1.0" for row in rows)
    assert all(row["task_id"].startswith("synthetic-") for row in rows)
