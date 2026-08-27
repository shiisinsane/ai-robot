"""W2 分析仓库 DDL、维度种子和字典映射测试。"""

from pathlib import Path
import sqlite3

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
DDL = ROOT / "schemas" / "common" / "warehouse.sql"
SEEDS = ROOT / "schemas" / "common" / "seed_dimensions.sql"
DICTIONARY = ROOT / "schemas" / "common" / "data_dictionary.yaml"


@pytest.fixture()
def database():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(DDL.read_text(encoding="utf-8"))
    connection.executescript(SEEDS.read_text(encoding="utf-8"))
    try:
        yield connection
    finally:
        connection.close()


def table_names(connection):
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {row[0] for row in rows}


def columns(connection, table):
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def test_expected_star_schema_tables_exist(database):
    expected = {
        "dim_robot", "dim_scenario", "dim_route", "dim_parameter_version",
        "dim_error_code", "dim_experiment", "fact_robot_operation_window",
        "fact_task_execution", "fact_task_event", "fact_task_telemetry_1s",
    }
    assert expected <= table_names(database)


def test_dictionary_required_columns_exist_in_ddl(database):
    dictionary = yaml.safe_load(DICTIONARY.read_text(encoding="utf-8"))
    for table, definition in dictionary["tables"].items():
        assert set(definition["required_columns"]) <= columns(database, table), table


def test_m6_error_code_dimension_is_complete(database):
    rows = database.execute(
        "SELECT error_code, analytical_terminal_status FROM dim_error_code ORDER BY error_code"
    ).fetchall()
    assert {row[0] for row in rows} == {
        0, 100, 101, 102, 103, 200, 201, 202, 203, 300, 301, 400, 500
    }
    assert dict(rows)[203] == "timeout"
    assert dict(rows)[103] == "rejected"


def insert_minimum_dimensions(database):
    database.execute(
        "INSERT INTO dim_robot VALUES (?, ?, ?, ?, ?, ?)",
        ("sim-01", "仿真机器人", "differential_drive_sim", True,
         "2026-08-19 00:00:00", None),
    )
    database.execute(
        "INSERT INTO dim_scenario VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("scenario-01", "基线", "map-01", "A", "B", "short", "low", "none",
         "v1", None),
    )
    database.execute(
        "INSERT INTO dim_route VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("route-01", "map-01", "A到B", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0, "v1"),
    )
    database.execute(
        "INSERT INTO dim_parameter_version VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("param-v1", "config/common/m5_navigation.yaml", "a" * 64,
         "m6.task.v1", "m1.v2", 0.35, 1.0, 0.5, "2026-08-19 00:00:00"),
    )
    database.execute(
        "INSERT INTO dim_experiment VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("roa-20260819-baseline-001", "baseline", "ROA-W2-example",
         "roa-data-v0.0", "roa-metrics-v1.0", "roa-schema-v1.0", "abcdef0", True,
         81, "roa_w2_001", "natural", None, 0.0, 10.0,
         "2026-08-19 00:00:00", "2026-08-19 00:00:10", True, None,
         "portfolio/robot_ops_analytics/configs/example.yaml",
         "portfolio/robot_ops_analytics/schemas/evidence/evidence_manifest.yaml"),
    )


def test_valid_minimum_task_can_be_inserted(database):
    insert_minimum_dimensions(database)
    database.execute(
        """INSERT INTO fact_task_execution (
               task_id, request_id, experiment_id, robot_id, scenario_id, route_id,
               parameter_version, task_type, sensing_mode, task_timeout_sec,
               target_frame, target_x_m, target_y_m, target_yaw_rad, requested_at_sim,
               accepted_at_sim, terminal_at_sim, accepted, terminal_status, error_code,
               effective_task, data_quality_valid
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("task-001", "request-001", "roa-20260819-baseline-001", "sim-01",
         "scenario-01", "route-01", "param-v1", 1, 1, 90.0, "map", 1.0, 0.0,
         0.0, 1.0, 1.1, 5.0, True, "success", 0, True, True),
    )
    assert database.execute("SELECT COUNT(*) FROM fact_task_execution").fetchone()[0] == 1


def test_rejected_task_requires_rejection_reason(database):
    insert_minimum_dimensions(database)
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            """INSERT INTO fact_task_execution (
                   task_id, request_id, experiment_id, robot_id, scenario_id, route_id,
                   parameter_version, task_type, sensing_mode, task_timeout_sec,
                   target_frame, target_x_m, target_y_m, target_yaw_rad, requested_at_sim,
                   accepted, terminal_status, error_code, effective_task, data_quality_valid
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("task-rejected", "request-002", "roa-20260819-baseline-001", "sim-01",
             "scenario-01", "route-01", "param-v1", 1, 1, 90.0, "map", 1.0, 0.0,
             0.0, 2.0, False, "rejected", 103, True, True),
        )


def test_telemetry_valid_buckets_cannot_exceed_expected(database):
    insert_minimum_dimensions(database)
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            """INSERT INTO fact_task_execution (
                   task_id, request_id, experiment_id, robot_id, scenario_id, route_id,
                   parameter_version, task_type, sensing_mode, task_timeout_sec,
                   target_frame, target_x_m, target_y_m, target_yaw_rad, requested_at_sim,
                   accepted_at_sim, terminal_at_sim, accepted, terminal_status, error_code,
                   effective_task, data_quality_valid, telemetry_expected_bucket_count,
                   telemetry_valid_bucket_count
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("task-bad-buckets", "request-003", "roa-20260819-baseline-001", "sim-01",
             "scenario-01", "route-01", "param-v1", 1, 1, 90.0, "map", 1.0, 0.0,
             0.0, 2.0, 2.1, 4.0, True, "success", 0, True, True, 2, 3),
        )


def test_metric_dictionary_has_a_mapping_for_every_w1_metric():
    w1 = yaml.safe_load(
        (ROOT / "schemas" / "common" / "metric_dictionary.yaml").read_text(encoding="utf-8")
    )
    w2 = yaml.safe_load(DICTIONARY.read_text(encoding="utf-8"))
    metric_ids = {metric["id"] for metric in w1["metrics"]}
    assert metric_ids == set(w2["metric_field_mapping"])


def test_every_metric_mapping_references_existing_columns(database):
    dictionary = yaml.safe_load(DICTIONARY.read_text(encoding="utf-8"))

    def field_references(value):
        if isinstance(value, str):
            return [value] if "." in value else []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str) and "." in item]
        if isinstance(value, dict):
            references = []
            for nested in value.values():
                references.extend(field_references(nested))
            return references
        return []

    for metric_id, mapping in dictionary["metric_field_mapping"].items():
        for reference in field_references(mapping):
            table, column = reference.split(".", 1)
            assert table in table_names(database), (metric_id, reference)
            assert column in columns(database, table), (metric_id, reference)
