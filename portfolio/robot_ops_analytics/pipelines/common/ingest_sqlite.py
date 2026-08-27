"""按W5审计白名单将W4 JSONL幂等接入SQLite原始层。"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import time
from typing import Any


SCHEMA = Path(__file__).parents[2] / "schemas/common/raw_ingestion_sqlite.sql"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _key(dataset_version: str, batch_id: str, source_file: str,
         line_number: int, payload_sha256: str) -> str:
    material = "|".join((dataset_version, batch_id, source_file,
                         str(line_number), payload_sha256))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database, timeout=30)
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _with_lock_retry(operation, attempts: int = 8):
    """对SQLite瞬时写锁进行有界退避；其他数据库错误原样抛出。"""
    for attempt in range(attempts):
        try:
            return operation()
        except sqlite3.OperationalError as error:
            if "locked" not in str(error).lower() or attempt == attempts - 1:
                raise
            time.sleep(min(0.02 * (2 ** attempt), 0.5))


def _manifest_tasks(manifest: dict[str, Any]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in manifest.get("tasks", []):
        grouped[row["batch_id"]].add(row["task_id"])
    if not grouped:
        raise ValueError("审计清单没有入组任务")
    return grouped


def ingest_dataset(database: Path, manifest_path: Path,
                   source_root: Path | None = None,
                   batch_ids: list[str] | None = None,
                   reverse_batches: bool = False,
                   max_delay_seconds: float = 0.0,
                   fail_after_records: int | None = None) -> dict[str, int | str | bool]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("quality_gate_passed"):
        raise ValueError("W5审计清单未通过质量门禁")
    dataset_version = manifest["dataset_version"]
    root = source_root or Path(manifest["source_root"])
    allowed = _manifest_tasks(manifest)
    if batch_ids is not None:
        unknown = sorted(set(batch_ids) - set(allowed))
        if unknown:
            raise ValueError(f"批次不在审计清单中：{unknown}")
        allowed = {batch_id: allowed[batch_id] for batch_id in batch_ids}
        if not allowed:
            raise ValueError("没有可接入的批次")
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(database)
    _with_lock_retry(lambda: initialize(connection))
    seen = inserted = duplicates = 0
    imported_tasks: set[str] = set()
    now = _now()
    try:
        batches = sorted(allowed.items(), reverse=reverse_batches)
        for batch_id, task_ids in batches:
            if max_delay_seconds > 0:
                time.sleep(random.uniform(0, max_delay_seconds))
            batch_dir = root / batch_id
            ingestion_id = hashlib.sha256(
                f"{dataset_version}|{batch_id}".encode("utf-8")).hexdigest()
            def ingest_batch() -> None:
                nonlocal seen, inserted, duplicates
                with connection:
                    connection.execute(
                    """INSERT INTO ingestion_batch (
                           ingestion_batch_id, dataset_version, source_batch_id,
                           source_uri, first_ingested_at, last_replayed_at, replay_count)
                       VALUES (?, ?, ?, ?, ?, ?, 1)
                       ON CONFLICT(dataset_version, source_batch_id) DO UPDATE SET
                           last_replayed_at=excluded.last_replayed_at,
                           replay_count=ingestion_batch.replay_count + 1""",
                        (ingestion_id, dataset_version, batch_id, str(batch_dir.resolve()), now, now))
                    sources = (
                        ("run_results.jsonl", batch_dir / "batch_runner/run_results.jsonl"),
                        ("records.jsonl", batch_dir / "structured/records.jsonl"),
                    )
                    for source_file, path in sources:
                        last_line = 0
                        for line_number, line in enumerate(
                                path.read_text(encoding="utf-8").splitlines(), start=1):
                            last_line = line_number
                            if not line.strip():
                                continue
                            row = json.loads(line)
                            task_id = row.get("task_id")
                            if task_id not in task_ids:
                                continue
                            seen += 1
                            imported_tasks.add(task_id)
                            payload = _canonical(row)
                            payload_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                            key = _key(dataset_version, batch_id, source_file,
                                       line_number, payload_sha)
                            record_type = (row.get("record_type") or
                                           ("run_result" if source_file == "run_results.jsonl"
                                            else "unknown"))
                            cursor = connection.execute(
                            """INSERT OR IGNORE INTO raw_record (
                                   idempotency_key, ingestion_batch_id, dataset_version,
                                   source_batch_id, source_file, source_line_number,
                                   record_type, task_id, event_time_sim, payload_sha256,
                                   payload_json, received_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (key, ingestion_id, dataset_version, batch_id, source_file,
                                 line_number, record_type, task_id, row.get("event_time_sim"),
                                 payload_sha, payload, now))
                            if cursor.rowcount == 1:
                                inserted += 1
                            else:
                                duplicates += 1
                            if fail_after_records is not None and seen >= fail_after_records:
                                raise RuntimeError("注入接入中断")
                        connection.execute(
                        """INSERT INTO etl_checkpoint (
                               dataset_version, source_batch_id, source_file,
                               last_scanned_line, updated_at)
                           VALUES (?, ?, ?, ?, ?)
                           ON CONFLICT(dataset_version, source_batch_id, source_file)
                           DO UPDATE SET last_scanned_line=excluded.last_scanned_line,
                                         updated_at=excluded.updated_at""",
                            (dataset_version, batch_id, source_file, last_line, now))

            _with_lock_retry(ingest_batch)
        missing = sorted(set().union(*allowed.values()) - imported_tasks)
        if missing:
            raise ValueError(f"白名单任务未导入：{missing}")
        total_records = connection.execute(
            "SELECT COUNT(*) FROM raw_record WHERE dataset_version=?",
            (dataset_version,)).fetchone()[0]
        unique_tasks = connection.execute(
            "SELECT COUNT(DISTINCT task_id) FROM raw_record WHERE dataset_version=?",
            (dataset_version,)).fetchone()[0]
        replay_count = connection.execute(
            "SELECT SUM(replay_count) FROM ingestion_batch WHERE dataset_version=?",
            (dataset_version,)).fetchone()[0]
    finally:
        connection.close()
    return {
        "dataset_version": dataset_version,
        "quality_gate_passed": not missing,
        "records_seen": seen,
        "records_inserted": inserted,
        "duplicates_ignored": duplicates,
        "stored_records": total_records,
        "unique_tasks": unique_tasks,
        "batch_replay_count": replay_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--batch-id", action="append", dest="batch_ids")
    parser.add_argument("--reverse-batches", action="store_true")
    parser.add_argument("--max-delay-seconds", type=float, default=0.0)
    parser.add_argument("--fail-after-records", type=int)
    args = parser.parse_args()
    report = ingest_dataset(
        args.database, args.manifest, args.source_root, args.batch_ids,
        args.reverse_batches, args.max_delay_seconds, args.fail_after_records)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
