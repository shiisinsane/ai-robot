import json
from pathlib import Path
import sqlite3

from portfolio.robot_ops_analytics.etl.ingest_sqlite import ingest_dataset


def fixture(tmp_path: Path):
    root = tmp_path / "source"
    batch = root / "batch-1"
    (batch / "batch_runner").mkdir(parents=True)
    (batch / "structured").mkdir()
    run_rows = [
        {"task_id": "task-1", "return_code": 0},
        {"task_id": "excluded", "return_code": 0},
    ]
    records = [
        {"task_id": "task-1", "record_type": "task_context",
         "event": "requested", "event_time_sim": 1.0},
        {"task_id": "task-1", "record_type": "task_context",
         "event": "terminal", "event_time_sim": 2.0},
        {"task_id": "excluded", "record_type": "task_context",
         "event": "terminal", "event_time_sim": 2.0},
    ]
    (batch / "batch_runner/run_results.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in run_rows), encoding="utf-8")
    (batch / "structured/records.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    manifest = {
        "dataset_version": "test-v1", "source_root": str(root),
        "quality_gate_passed": True,
        "tasks": [{"batch_id": "batch-1", "task_id": "task-1"}],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return root, manifest_path


def test_ingestion_is_idempotent_and_respects_manifest_allowlist(tmp_path):
    _, manifest = fixture(tmp_path)
    database = tmp_path / "raw.sqlite"
    first = ingest_dataset(database, manifest)
    second = ingest_dataset(database, manifest)
    assert first["records_seen"] == first["records_inserted"] == 3
    assert first["duplicates_ignored"] == 0
    assert second["records_inserted"] == 0
    assert second["duplicates_ignored"] == 3
    assert second["stored_records"] == 3
    assert second["unique_tasks"] == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM raw_record WHERE task_id='excluded'").fetchone()[0] == 0
        assert connection.execute(
            "SELECT replay_count FROM ingestion_batch").fetchone()[0] == 2


def test_ingestion_rejects_manifest_that_failed_quality_gate(tmp_path):
    _, manifest = fixture(tmp_path)
    data = json.loads(manifest.read_text())
    data["quality_gate_passed"] = False
    manifest.write_text(json.dumps(data), encoding="utf-8")
    try:
        ingest_dataset(tmp_path / "raw.sqlite", manifest)
    except ValueError as error:
        assert "未通过质量门禁" in str(error)
    else:
        raise AssertionError("未通过审计的清单不应进入接入层")
