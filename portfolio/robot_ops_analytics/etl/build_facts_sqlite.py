"""将SQLite raw_record增量加工为任务、事件和整秒遥测事实表。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any


SCHEMA = Path(__file__).parents[1] / "schemas/analytics_facts_sqlite.sql"
PIPELINE = "raw_to_analysis_facts_v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_type(row: dict[str, Any]) -> str:
    if row["event"] != "feedback":
        if row["event"] == "terminal":
            if row.get("error_code") == 203:
                return "timeout"
            return "succeeded" if row.get("success") else "failed"
        return row["event"]
    return {1: "accepted", 2: "validating", 3: "navigating", 4: "sensing"}.get(
        row.get("phase"), "feedback_unknown")


def _terminal_status(row: dict[str, Any]) -> str:
    if row.get("error_code") == 203:
        return "timeout"
    if row.get("success"):
        return "success"
    if row.get("action_status") == 5:
        return "canceled"
    return "failed"


def build_facts(database: Path, fail_after_tasks: int | None = None) -> dict[str, Any]:
    connection = sqlite3.connect(database, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    try:
        previous = connection.execute(
            "SELECT last_raw_record_id FROM fact_etl_checkpoint WHERE pipeline_name=?",
            (PIPELINE,)).fetchone()
        previous_id = previous[0] if previous else 0
        current_id = connection.execute(
            "SELECT COALESCE(MAX(raw_record_id), 0) FROM raw_record").fetchone()[0]
        affected = [row[0] for row in connection.execute(
            "SELECT DISTINCT task_id FROM raw_record WHERE raw_record_id > ? ORDER BY task_id",
            (previous_id,))]
        with connection:
            for task_index, task_id in enumerate(affected, start=1):
                raw_rows = connection.execute(
                    """SELECT raw_record_id, dataset_version, source_batch_id, record_type,
                              payload_json
                       FROM raw_record WHERE task_id=? ORDER BY raw_record_id""",
                    (task_id,)).fetchall()
                decoded = [(row, json.loads(row["payload_json"])) for row in raw_rows]
                run_rows = [(row, data) for row, data in decoded if row["record_type"] == "run_result"]
                contexts = [(row, data) for row, data in decoded if row["record_type"] == "task_context"]
                telemetry = [(row, data) for row, data in decoded
                             if row["record_type"] == "task_telemetry_1s"]
                requested = [data for _, data in contexts if data.get("event") == "requested"]
                accepted = [data for _, data in contexts if data.get("event") == "accepted"]
                terminal = [data for _, data in contexts if data.get("event") == "terminal"]
                if len(run_rows) != 1 or len(requested) != 1 or len(accepted) != 1 or len(terminal) != 1:
                    raise ValueError(f"任务事实来源不唯一：{task_id}")
                raw_meta, run = run_rows[0]
                req, acc, term = requested[0], accepted[0], terminal[0]
                valid_buckets = sum(bool(data.get("required_topics_present")) and
                                    bool(data.get("timestamp_valid")) for _, data in telemetry)
                max_speed = max((data["max_abs_linear_speed_mps"] for _, data in telemetry
                                 if data.get("max_abs_linear_speed_mps") is not None), default=None)
                min_scan = min((data["minimum_valid_scan_range_m"] for _, data in telemetry
                                if data.get("minimum_valid_scan_range_m") is not None), default=None)
                values = (
                    task_id, raw_meta["dataset_version"], raw_meta["source_batch_id"],
                    run["experiment_id"], req["request_id"], run["route_id"],
                    run["environment_profile"], run["obstacle_profile"],
                    run["initial_perturbation"], run["parameter_profile"], run["run_origin"],
                    run.get("fault_injection_type"), run["timeout_sec"], run["start_x"],
                    run["start_y"], run["start_yaw"], run["target_x"], run["target_y"],
                    run["target_yaw"], req["event_time_sim"], acc["event_time_sim"],
                    term["event_time_sim"], run["started_at"], run["finished_at"], 1,
                    _terminal_status(term), int(bool(term.get("success"))), term["error_code"],
                    term.get("message"), term["event_time_sim"] - acc["event_time_sim"],
                    len(telemetry), valid_buckets, max_speed, min_scan,
                    int(valid_buckets == len(telemetry)), max(row["raw_record_id"] for row in raw_rows))
                connection.execute(
                    """INSERT OR REPLACE INTO fact_task_execution VALUES (
                           ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    values)
                connection.execute("DELETE FROM fact_task_event WHERE task_id=?", (task_id,))
                for sequence, (row, data) in enumerate(contexts, start=1):
                    connection.execute(
                        "INSERT INTO fact_task_event VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (row["raw_record_id"], task_id, sequence, data["event_time_sim"],
                         _event_type(data), data.get("phase"), data.get("progress"),
                         data.get("error_code"), data.get("message"), data["request_id"]))
                connection.execute("DELETE FROM fact_task_telemetry_1s WHERE task_id=?", (task_id,))
                for row, data in telemetry:
                    columns = [
                        row["raw_record_id"], task_id, data["bucket_start_sim"], data["bucket_end_sim"],
                        data["sample_count_odom"], data["sample_count_pose"], data["sample_count_scan"],
                        data["sample_count_safety"], int(data["required_topics_present"]),
                        int(data["timestamp_valid"]), data.get("pose_x_m"), data.get("pose_y_m"),
                        data.get("pose_yaw_rad"), data.get("pose_covariance_x"),
                        data.get("pose_covariance_y"), data.get("pose_covariance_yaw"),
                        data.get("mean_linear_speed_mps"), data.get("max_abs_linear_speed_mps"),
                        data.get("mean_angular_speed_rps"), data.get("max_abs_angular_speed_rps"),
                        data.get("minimum_valid_scan_range_m"), data.get("safety_stop_active"),
                        data.get("stale_sensor_mask", 0)]
                    connection.execute(
                        "INSERT INTO fact_task_telemetry_1s VALUES (" + ",".join("?" * len(columns)) + ")",
                        columns)
                if fail_after_tasks is not None and task_index >= fail_after_tasks:
                    raise RuntimeError("注入事实层加工中断")
            connection.execute(
                """INSERT INTO fact_etl_checkpoint VALUES (?, ?, ?)
                   ON CONFLICT(pipeline_name) DO UPDATE SET
                     last_raw_record_id=excluded.last_raw_record_id, updated_at=excluded.updated_at""",
                (PIPELINE, current_id, _now()))
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("fact_task_execution", "fact_task_event", "fact_task_telemetry_1s")}
        return {"quality_gate_passed": True, "previous_raw_record_id": previous_id,
                "current_raw_record_id": current_id, "affected_tasks": len(affected), **counts}
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = build_facts(args.database)
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
