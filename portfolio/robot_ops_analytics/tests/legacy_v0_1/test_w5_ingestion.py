import json
import multiprocessing
from pathlib import Path
import sqlite3

from portfolio.robot_ops_analytics.pipelines.common.ingest_sqlite import ingest_dataset


def _concurrent_ingest(database, manifest, batch_ids, reverse, queue):
    try:
        queue.put(ingest_dataset(
            Path(database), Path(manifest), batch_ids=batch_ids,
            reverse_batches=reverse, max_delay_seconds=0.02))
    except Exception as error:  # pragma: no cover - 仅用于把子进程错误传回父进程
        queue.put({"error": repr(error)})


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


def concurrent_fixture(tmp_path: Path):
    root = tmp_path / "concurrent-source"
    tasks = []
    for index in range(4):
        batch_id = f"batch-{index}"
        task_id = f"task-{index}"
        batch = root / batch_id
        (batch / "batch_runner").mkdir(parents=True)
        (batch / "structured").mkdir()
        (batch / "batch_runner/run_results.jsonl").write_text(
            json.dumps({"task_id": task_id, "return_code": 0}) + "\n",
            encoding="utf-8")
        rows = [
            {"task_id": task_id, "record_type": "task_context",
             "event": "requested", "event_time_sim": 1.0},
            {"task_id": task_id, "record_type": "task_context",
             "event": "terminal", "event_time_sim": 2.0},
        ]
        (batch / "structured/records.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        tasks.append({"batch_id": batch_id, "task_id": task_id})
    manifest = {
        "dataset_version": "concurrent-v1", "source_root": str(root),
        "quality_gate_passed": True, "tasks": tasks,
    }
    manifest_path = tmp_path / "concurrent-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


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


def test_wal_concurrent_replay_handles_overlap_and_reverse_order(tmp_path):
    manifest = concurrent_fixture(tmp_path)
    database = tmp_path / "concurrent.sqlite"
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    workers = [
        context.Process(target=_concurrent_ingest, args=(
            database, manifest, ["batch-0", "batch-1", "batch-2"], False, queue)),
        context.Process(target=_concurrent_ingest, args=(
            database, manifest, ["batch-3", "batch-2", "batch-1"], True, queue)),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=20)
        assert worker.exitcode == 0
    reports = [queue.get(timeout=2) for _ in workers]
    assert not any("error" in report for report in reports)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("SELECT COUNT(*) FROM raw_record").fetchone()[0] == 12
        assert connection.execute(
            "SELECT COUNT(DISTINCT task_id) FROM raw_record").fetchone()[0] == 4
        assert connection.execute("SELECT COUNT(*) FROM etl_checkpoint").fetchone()[0] == 8
        assert connection.execute(
            "SELECT SUM(replay_count) FROM ingestion_batch").fetchone()[0] == 6


def test_interrupted_batch_rolls_back_and_full_replay_recovers(tmp_path):
    _, manifest = fixture(tmp_path)
    database = tmp_path / "interrupted.sqlite"
    try:
        ingest_dataset(database, manifest, fail_after_records=2)
    except RuntimeError as error:
        assert "注入接入中断" in str(error)
    else:
        raise AssertionError("故障注入应中断接入")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM raw_record").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM etl_checkpoint").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM ingestion_batch").fetchone()[0] == 0
    recovered = ingest_dataset(database, manifest)
    assert recovered["records_inserted"] == 3
    assert recovered["unique_tasks"] == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
