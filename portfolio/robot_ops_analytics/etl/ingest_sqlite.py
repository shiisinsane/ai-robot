"""按W5审计白名单将W4 JSONL幂等接入SQLite原始层。"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


SCHEMA = Path(__file__).parents[1] / "schemas/raw_ingestion_sqlite.sql"


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


def _manifest_tasks(manifest: dict[str, Any]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in manifest.get("tasks", []):
        grouped[row["batch_id"]].add(row["task_id"])
    if not grouped:
        raise ValueError("审计清单没有入组任务")
    return grouped


def ingest_dataset(database: Path, manifest_path: Path,
                   source_root: Path | None = None) -> dict[str, int | str | bool]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("quality_gate_passed"):
        raise ValueError("W5审计清单未通过质量门禁")
    dataset_version = manifest["dataset_version"]
    root = source_root or Path(manifest["source_root"])
    allowed = _manifest_tasks(manifest)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database, timeout=30)
    connection.execute("PRAGMA busy_timeout = 30000")
    initialize(connection)
    seen = inserted = duplicates = 0
    imported_tasks: set[str] = set()
    now = _now()
    try:
        for batch_id, task_ids in sorted(allowed.items()):
            batch_dir = root / batch_id
            ingestion_id = hashlib.sha256(
                f"{dataset_version}|{batch_id}".encode("utf-8")).hexdigest()
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
                    connection.execute(
                        """INSERT INTO etl_checkpoint (
                               dataset_version, source_batch_id, source_file,
                               last_scanned_line, updated_at)
                           VALUES (?, ?, ?, ?, ?)
                           ON CONFLICT(dataset_version, source_batch_id, source_file)
                           DO UPDATE SET last_scanned_line=excluded.last_scanned_line,
                                         updated_at=excluded.updated_at""",
                        (dataset_version, batch_id, source_file, last_line, now))
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
        "quality_gate_passed": unique_tasks == len(set().union(*allowed.values())),
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
    args = parser.parse_args()
    report = ingest_dataset(args.database, args.manifest, args.source_root)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
