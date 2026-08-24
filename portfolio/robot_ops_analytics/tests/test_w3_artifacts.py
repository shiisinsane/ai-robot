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
    assert "_partial_start_buckets" in text
    assert "math.floor(now)" in text
    assert "next_task_id != self._task_id" in text
    assert "row[\"bucket_end_sim\"] <= started_at" in text
    assert "_partial_end_buckets" in text


def test_orchestrator_only_publishes_internal_context():
    text = (ROOT / "orchestrator/run_experiment.py").read_text(encoding="utf-8")
    assert 'ActionClient(self, ExecuteRobotTask, "task/execute")' in text
    assert 'String, "analytics/task_context"' in text
    assert "self.context =" not in text
    assert "cmd_vel" not in text
    assert "_wait_ready" in text
    assert "_wait_collector" in text
    assert "_warm_task_telemetry" in text
    assert 'count_subscribers("analytics/task_context")' in text
    assert "not self._safety_stop" in text
    assert 'create_client(Trigger, "safety/clear_faults")' in text
    assert text.index("required <= self._seen and clock_advancing") < text.index(
        "self._clear_faults.call_async")
    start_body = text[text.index("    def start(self):"):text.index(
        "    def _publish_context", text.index("    def start(self):"))]
    assert start_body.index("self._wait_collector()") < start_body.index(
        "self._wait_ready()")
    assert start_body.index('self._publish_context(True, "requested")') < start_body.index(
        "self._warm_task_telemetry()") < start_body.index("self.client.send_goal_async")


def test_synthetic_fixture_is_valid_jsonl_and_explicitly_synthetic():
    rows = [json.loads(line) for line in (ROOT / "samples/w3_synthetic_fixture.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 3
    assert all(row["schema_version"] == "roa-schema-v1.0" for row in rows)
    assert all(row["task_id"].startswith("synthetic-") for row in rows)
