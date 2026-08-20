import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("roa_core", ROOT / "collector" / "core.py")
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)


def test_feedback_is_deduplicated_by_phase_and_clock_jump_is_marked():
    recorder = core.TaskRecorder("exp-1", "task-1", "request-1", 10.0)
    assert recorder.add_feedback(10.1, 2, 0.1, "校验") is not None
    assert recorder.add_feedback(10.2, 2, 0.2, "仍在校验") is None
    recorder.add_feedback(9.9, 3, 0.3, "导航")
    assert recorder.clock_valid is False
    assert [event["event_sequence"] for event in recorder.events] == [1, 2]


def test_bucket_uses_last_pose_and_aggregates_values():
    buckets = core.TelemetryBucketAggregator()
    buckets.add_odom("task-1", 3.1, 0.2, -0.1)
    buckets.add_odom("task-1", 3.8, 0.4, 0.3)
    buckets.add_pose("task-1", 3.2, 1, 2, 0.1, 0.01, 0.02, 0.03)
    buckets.add_pose("task-1", 3.9, 2, 3, 0.2, 0.04, 0.05, 0.06)
    buckets.add_scan("task-1", 3.4, [float("nan"), float("inf"), 0.05, 0.7, 2.0], 0.1, 1.5)
    buckets.add_safety("task-1", 3.5, False)
    row = buckets.rows()[0]
    assert row["required_topics_present"] is True
    assert row["mean_linear_speed_mps"] == pytest.approx(0.3)
    assert row["max_abs_angular_speed_rps"] == pytest.approx(0.3)
    assert row["pose_x_m"] == 2
    assert row["minimum_valid_scan_range_m"] == 0.7


def test_missing_topic_and_backward_topic_stamp_are_visible():
    buckets = core.TelemetryBucketAggregator()
    buckets.add_odom("task-1", 8.2, 0, 0)
    buckets.add_odom("task-1", 7.9, 0, 0)
    rows = buckets.rows()
    assert rows[0]["timestamp_valid"] is False
    assert all(row["required_topics_present"] is False for row in rows)


def test_jsonl_sink_writes_machine_readable_schema(tmp_path):
    target = tmp_path / "nested" / "records.jsonl"
    core.JsonlSink(target).append("task_event", {"task_id": "任务-1"})
    row = json.loads(target.read_text(encoding="utf-8"))
    assert row == {"record_type": "task_event", "schema_version": "roa-schema-v1.0", "task_id": "任务-1"}
