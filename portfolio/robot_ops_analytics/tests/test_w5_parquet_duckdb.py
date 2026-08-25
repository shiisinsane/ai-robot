import importlib.util
from pathlib import Path
import sqlite3

import pytest


ANALYTICS_DEPS = all(importlib.util.find_spec(name) for name in ("duckdb", "pyarrow"))


@pytest.mark.skipif(not ANALYTICS_DEPS, reason="需要DuckDB和PyArrow分析环境")
def test_sqlite_parquet_duckdb_reconciliation(tmp_path: Path):
    from portfolio.robot_ops_analytics.etl.export_parquet_duckdb import export_analysis

    database = tmp_path / "analysis.sqlite"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE fact_task_execution (
              task_id TEXT, dataset_version TEXT, terminal_status TEXT);
            CREATE TABLE fact_task_event (
              task_id TEXT, event_sequence INTEGER, event_time_sim DOUBLE, event_type TEXT);
            CREATE TABLE fact_task_telemetry_1s (
              task_id TEXT, bucket_start_sim DOUBLE, bucket_end_sim DOUBLE);
            INSERT INTO fact_task_execution VALUES ('t1', 'v1', 'success');
            INSERT INTO fact_task_event VALUES ('t1', 1, 1.0, 'requested');
            INSERT INTO fact_task_event VALUES ('t1', 2, 2.0, 'succeeded');
            INSERT INTO fact_task_telemetry_1s VALUES ('t1', 1.0, 2.0);
        """)
    report = export_analysis(database, tmp_path / "parquet", tmp_path / "analysis.duckdb")
    assert report["quality_gate_passed"] is True
    assert report["join_distinct_tasks"] == 1
    assert all(check["passed"] for check in report["table_checks"])
