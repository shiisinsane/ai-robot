"""将W5 SQLite事实表导出为Parquet，并创建DuckDB分析视图与对账报告。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq


TABLES = {
    "fact_task_execution": {
        "key": ["task_id"],
        "required": ["task_id", "dataset_version", "terminal_status"],
    },
    "fact_task_event": {
        "key": ["task_id", "event_sequence"],
        "required": ["task_id", "event_sequence", "event_time_sim", "event_type"],
    },
    "fact_task_telemetry_1s": {
        "key": ["task_id", "bucket_start_sim"],
        "required": ["task_id", "bucket_start_sim", "bucket_end_sim"],
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def _sqlite_table(connection: sqlite3.Connection, table: str) -> pa.Table:
    cursor = connection.execute(f"SELECT * FROM {table}")
    names = [item[0] for item in cursor.description]
    rows = [dict(zip(names, row)) for row in cursor.fetchall()]
    if not rows:
        raise ValueError(f"事实表为空：{table}")
    return pa.Table.from_pylist(rows)


def export_analysis(sqlite_database: Path, parquet_dir: Path,
                    duckdb_database: Path, dataset_version: str = "roa-data-v0.1",
                    export_version: str = "roa-parquet-v0.1") -> dict[str, Any]:
    parquet_dir.mkdir(parents=True, exist_ok=True)
    duckdb_database.parent.mkdir(parents=True, exist_ok=True)
    sqlite_counts: dict[str, int] = {}
    parquet_files: dict[str, dict[str, Any]] = {}

    with sqlite3.connect(sqlite_database) as sqlite_connection:
        for table in TABLES:
            arrow_table = _sqlite_table(sqlite_connection, table)
            sqlite_counts[table] = arrow_table.num_rows
            target = parquet_dir / f"{table}.parquet"
            temporary = target.with_suffix(".parquet.tmp")
            pq.write_table(arrow_table, temporary, compression="zstd")
            temporary.replace(target)
            metadata = pq.read_metadata(target)
            parquet_files[table] = {
                "path": str(target),
                "rows": metadata.num_rows,
                "columns": metadata.num_columns,
                "size_bytes": target.stat().st_size,
                "sha256": _sha256(target),
            }

    duck = duckdb.connect(str(duckdb_database))
    try:
        duck.execute("""CREATE TABLE IF NOT EXISTS analysis_metadata (
                           dataset_version VARCHAR PRIMARY KEY,
                           generated_at TIMESTAMP,
                           source_sqlite VARCHAR,
                           export_version VARCHAR)""")
        duck.execute("DELETE FROM analysis_metadata WHERE dataset_version=?", [dataset_version])
        duck.execute(
            "INSERT INTO analysis_metadata VALUES (?, ?, ?, ?)",
            [dataset_version, _now(), str(sqlite_database.resolve()), export_version])
        for table in TABLES:
            path = _sql_path(parquet_dir / f"{table}.parquet")
            duck.execute(
                f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM read_parquet('{path}')")
        duckdb_counts = {table: duck.execute(
            f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES}
        checks = []
        for table, definition in TABLES.items():
            key = ", ".join(definition["key"])
            duplicates = duck.execute(
                f"SELECT COUNT(*) FROM (SELECT {key}, COUNT(*) n FROM {table} "
                f"GROUP BY {key} HAVING n > 1)").fetchone()[0]
            null_condition = " OR ".join(f"{column} IS NULL" for column in definition["required"])
            required_nulls = duck.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {null_condition}").fetchone()[0]
            checks.append({"table": table, "sqlite_rows": sqlite_counts[table],
                           "parquet_rows": parquet_files[table]["rows"],
                           "duckdb_rows": duckdb_counts[table],
                           "duplicate_keys": duplicates,
                           "required_null_rows": required_nulls,
                           "passed": sqlite_counts[table] == parquet_files[table]["rows"] ==
                           duckdb_counts[table] and duplicates == 0 and required_nulls == 0})
        join_distinct_tasks = duck.execute(
            """SELECT COUNT(DISTINCT t.task_id)
               FROM fact_task_execution t
               LEFT JOIN fact_task_event e USING (task_id)
               LEFT JOIN fact_task_telemetry_1s m USING (task_id)""").fetchone()[0]
        task_count = duckdb_counts["fact_task_execution"]
    finally:
        duck.close()

    passed = all(check["passed"] for check in checks) and join_distinct_tasks == task_count
    return {
        "dataset_version": dataset_version,
        "export_version": export_version,
        "generated_at": _now(),
        "quality_gate_passed": passed,
        "sqlite_database": str(sqlite_database),
        "duckdb_database": str(duckdb_database),
        "duckdb_size_bytes": duckdb_database.stat().st_size,
        "duckdb_sha256": _sha256(duckdb_database),
        "parquet_files": parquet_files,
        "table_checks": checks,
        "join_distinct_tasks": join_distinct_tasks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-database", type=Path, required=True)
    parser.add_argument("--parquet-dir", type=Path, required=True)
    parser.add_argument("--duckdb-database", type=Path, required=True)
    parser.add_argument("--dataset-version", default="roa-data-v0.1")
    parser.add_argument("--export-version", default="roa-parquet-v0.1")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = export_analysis(
        args.sqlite_database, args.parquet_dir, args.duckdb_database,
        args.dataset_version, args.export_version)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")
    if not report["quality_gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
