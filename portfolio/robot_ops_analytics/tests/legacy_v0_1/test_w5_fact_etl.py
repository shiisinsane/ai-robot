import json
from pathlib import Path
import sqlite3

import pytest

from portfolio.robot_ops_analytics.pipelines.common.build_facts_sqlite import build_facts
from portfolio.robot_ops_analytics.pipelines.common.audit_facts_sqlite import audit_facts
from portfolio.robot_ops_analytics.pipelines.common.ingest_sqlite import ingest_dataset


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    batch = root / "batch-1"
    (batch / "batch_runner").mkdir(parents=True)
    (batch / "structured").mkdir()
    run = {
        "task_id": "task-1", "experiment_id": "exp-1", "route_id": "short",
        "environment_profile": "natural__none__none__baseline",
        "obstacle_profile": "none", "initial_perturbation": "none",
        "parameter_profile": "baseline", "run_origin": "natural",
        "fault_injection_type": None, "timeout_sec": 90,
        "start_x": 0.0, "start_y": 0.0, "start_yaw": 0.0,
        "target_x": 1.0, "target_y": 0.0, "target_yaw": 0.0,
        "started_at": "2026-08-25T00:00:00+00:00",
        "finished_at": "2026-08-25T00:00:05+00:00", "return_code": 0,
    }
    records = [
        {"task_id": "task-1", "record_type": "task_context", "event": "requested",
         "event_time_sim": 1.0, "experiment_id": "exp-1", "request_id": "req-1"},
        {"task_id": "task-1", "record_type": "task_context", "event": "accepted",
         "event_time_sim": 1.1, "experiment_id": "exp-1", "request_id": "req-1"},
        {"task_id": "task-1", "record_type": "task_telemetry_1s",
         "bucket_start_sim": 1.0, "bucket_end_sim": 2.0, "sample_count_odom": 2,
         "sample_count_pose": 2, "sample_count_scan": 2, "sample_count_safety": 2,
         "required_topics_present": True, "timestamp_valid": True,
         "max_abs_linear_speed_mps": 0.2, "minimum_valid_scan_range_m": 0.8,
         "stale_sensor_mask": 0},
        {"task_id": "task-1", "record_type": "task_context", "event": "terminal",
         "event_time_sim": 3.0, "experiment_id": "exp-1", "request_id": "req-1",
         "success": True, "action_status": 4, "error_code": 0, "message": "ok"},
    ]
    (batch / "batch_runner/run_results.jsonl").write_text(json.dumps(run) + "\n")
    (batch / "structured/records.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in records))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"dataset_version": "v1", "source_root": str(root),
                                    "quality_gate_passed": True,
                                    "tasks": [{"batch_id": "batch-1", "task_id": "task-1"}]}))
    database = tmp_path / "facts.sqlite"
    ingest_dataset(database, manifest)
    return database


def test_fact_etl_builds_three_facts_and_second_run_is_incremental(tmp_path):
    database = _fixture(tmp_path)
    first = build_facts(database)
    second = build_facts(database)
    assert first["affected_tasks"] == 1
    assert first["fact_task_execution"] == 1
    assert first["fact_task_event"] == 3
    assert first["fact_task_telemetry_1s"] == 1
    assert second["affected_tasks"] == 0
    with sqlite3.connect(database) as connection:
        task = connection.execute(
            "SELECT terminal_status, cycle_time_sec, telemetry_bucket_count FROM fact_task_execution"
        ).fetchone()
        assert task == ("success", 1.9, 1)


def test_fact_etl_interruption_rolls_back_facts_and_checkpoint(tmp_path):
    database = _fixture(tmp_path)
    with pytest.raises(RuntimeError, match="加工中断"):
        build_facts(database, fail_after_tasks=1)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fact_task_execution").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM fact_etl_checkpoint").fetchone()[0] == 0
    recovered = build_facts(database)
    assert recovered["affected_tasks"] == 1


def test_fact_quality_and_join_reconciliation_pass_for_valid_data(tmp_path):
    database = _fixture(tmp_path)
    build_facts(database)
    report = audit_facts(database)
    assert report["quality_gate_passed"] is True
    assert report["rules_checked"] == 21
    assert report["join_check"]["distinct_tasks"] == 1


def test_fact_quality_detects_invalid_lifecycle_order(tmp_path):
    database = _fixture(tmp_path)
    build_facts(database)
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT raw_record_id, payload_json FROM raw_record "
            "WHERE record_type='task_context' AND json_extract(payload_json, '$.event')='terminal'"
        ).fetchone()
        payload = json.loads(row[1])
        payload["event_time_sim"] = 0.5
        connection.execute("UPDATE raw_record SET payload_json=? WHERE raw_record_id=?",
                           (json.dumps(payload), row[0]))
    report = audit_facts(database)
    failed = {rule["rule_id"] for rule in report["rules"] if not rule["passed"]}
    assert "DQ-TASK-002-lifecycle-order" in failed


def _mutate_raw_event(database: Path, event: str, changes: dict):
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT raw_record_id, payload_json FROM raw_record "
            "WHERE record_type='task_context' AND json_extract(payload_json, '$.event')=?",
            (event,)).fetchone()
        payload = json.loads(row[1])
        payload.update(changes)
        connection.execute("UPDATE raw_record SET payload_json=? WHERE raw_record_id=?",
                           (json.dumps(payload), row[0]))


@pytest.mark.parametrize(("event", "changes", "expected_rule"), [
    ("terminal", {"success": True, "error_code": 201},
     "DQ-TASK-008-terminal-error-consistency"),
    ("terminal", {"success": False, "error_code": 0},
     "DQ-TASK-009-failure-has-error-code"),
    ("accepted", {"request_id": "wrong-request"},
     "DQ-TASK-003-request-id-consistency"),
])
def test_fact_quality_detects_terminal_and_request_conflicts(
        tmp_path, event, changes, expected_rule):
    database = _fixture(tmp_path)
    build_facts(database)
    _mutate_raw_event(database, event, changes)
    report = audit_facts(database)
    failed = {rule["rule_id"] for rule in report["rules"] if not rule["passed"]}
    assert expected_rule in failed


def test_fact_quality_detects_missing_terminal(tmp_path):
    database = _fixture(tmp_path)
    build_facts(database)
    _mutate_raw_event(database, "terminal", {"event": "feedback", "phase": 3})
    report = audit_facts(database)
    failed = {rule["rule_id"] for rule in report["rules"] if not rule["passed"]}
    assert "DQ-TASK-001-lifecycle-cardinality" in failed


def test_fact_quality_detects_source_pollution(tmp_path):
    database = _fixture(tmp_path)
    build_facts(database)
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT raw_record_id, payload_json FROM raw_record WHERE record_type='run_result'"
        ).fetchone()
        payload = json.loads(row[1])
        payload["fault_injection_type"] = "unexpected_fault"
        connection.execute("UPDATE raw_record SET payload_json=? WHERE raw_record_id=?",
                           (json.dumps(payload), row[0]))
    report = audit_facts(database)
    failed = {rule["rule_id"] for rule in report["rules"] if not rule["passed"]}
    assert "DQ-SOURCE-001-run-origin-consistency" in failed
