"""审计W5 SQLite原始层、三类事实表及一对多Join口径。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any


KNOWN_PHASES = {1, 2, 3, 4}
KNOWN_ERROR_CODES = {0, 100, 101, 102, 103, 200, 201, 202, 203, 300, 301, 400, 500}


def _issue(rule_id: str, count: int, severity: str = "error") -> dict[str, Any]:
    return {"rule_id": rule_id, "severity": severity, "violations": count,
            "passed": count == 0}


def audit_facts(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        contexts: dict[str, list[dict[str, Any]]] = {}
        unknown_phases = unknown_errors = 0
        for row in connection.execute(
                "SELECT task_id, payload_json FROM raw_record WHERE record_type='task_context'"):
            data = json.loads(row["payload_json"])
            contexts.setdefault(row["task_id"], []).append(data)
            if data.get("event") == "feedback" and data.get("phase") not in KNOWN_PHASES:
                unknown_phases += 1
            if data.get("error_code") is not None and data["error_code"] not in KNOWN_ERROR_CODES:
                unknown_errors += 1

        missing_or_duplicate = invalid_order = request_mismatch = 0
        for rows in contexts.values():
            grouped = {name: [row for row in rows if row.get("event") == name]
                       for name in ("requested", "accepted", "terminal")}
            if any(len(grouped[name]) != 1 for name in grouped):
                missing_or_duplicate += 1
                continue
            requested, accepted, terminal = (grouped[name][0] for name in
                                             ("requested", "accepted", "terminal"))
            if not (requested["event_time_sim"] <= accepted["event_time_sim"] <=
                    terminal["event_time_sim"]):
                invalid_order += 1
            if len({row.get("request_id") for row in rows}) != 1:
                request_mismatch += 1

        raw_counts = {
            row[0]: row[1] for row in connection.execute(
                "SELECT record_type, COUNT(*) FROM raw_record GROUP BY record_type")}
        fact_counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("fact_task_execution", "fact_task_event", "fact_task_telemetry_1s")}
        raw_tasks = connection.execute(
            "SELECT COUNT(DISTINCT task_id) FROM raw_record WHERE record_type='run_result'").fetchone()[0]
        duplicate_buckets = connection.execute(
            """SELECT COUNT(*) FROM (
                   SELECT task_id, json_extract(payload_json, '$.bucket_start_sim'), COUNT(*) AS n
                   FROM raw_record WHERE record_type='task_telemetry_1s'
                   GROUP BY 1, 2 HAVING n > 1)""").fetchone()[0]
        invalid_telemetry = connection.execute(
            """SELECT COUNT(*) FROM fact_task_telemetry_1s
               WHERE bucket_end_sim <= bucket_start_sim OR required_topics_present=0
                  OR timestamp_valid=0""").fetchone()[0]
        task_reconciliation = abs(raw_tasks - fact_counts["fact_task_execution"])
        event_reconciliation = abs(raw_counts.get("task_context", 0) - fact_counts["fact_task_event"])
        telemetry_reconciliation = abs(
            raw_counts.get("task_telemetry_1s", 0) - fact_counts["fact_task_telemetry_1s"])
        join = connection.execute(
            """SELECT COUNT(*) AS joined_rows, COUNT(DISTINCT t.task_id) AS distinct_tasks
               FROM fact_task_execution t
               LEFT JOIN fact_task_event e ON e.task_id=t.task_id
               LEFT JOIN fact_task_telemetry_1s m ON m.task_id=t.task_id""").fetchone()
        join_distinct_mismatch = abs(join["distinct_tasks"] - fact_counts["fact_task_execution"])
        orphan_events = connection.execute(
            """SELECT COUNT(*) FROM fact_task_event e LEFT JOIN fact_task_execution t
               ON t.task_id=e.task_id WHERE t.task_id IS NULL""").fetchone()[0]
        orphan_telemetry = connection.execute(
            """SELECT COUNT(*) FROM fact_task_telemetry_1s m LEFT JOIN fact_task_execution t
               ON t.task_id=m.task_id WHERE t.task_id IS NULL""").fetchone()[0]

        rules = [
            _issue("DQ-TASK-001-lifecycle-cardinality", missing_or_duplicate),
            _issue("DQ-TASK-002-lifecycle-order", invalid_order),
            _issue("DQ-TASK-003-request-id-consistency", request_mismatch),
            _issue("DQ-EVENT-001-known-phase", unknown_phases),
            _issue("DQ-EVENT-002-known-error-code", unknown_errors),
            _issue("DQ-TELEMETRY-001-unique-bucket", duplicate_buckets),
            _issue("DQ-TELEMETRY-002-valid-bucket", invalid_telemetry),
            _issue("DQ-RECON-001-task-count", task_reconciliation),
            _issue("DQ-RECON-002-event-count", event_reconciliation),
            _issue("DQ-RECON-003-telemetry-count", telemetry_reconciliation),
            _issue("DQ-JOIN-001-distinct-task-preserved", join_distinct_mismatch),
            _issue("DQ-JOIN-002-orphan-event", orphan_events),
            _issue("DQ-JOIN-003-orphan-telemetry", orphan_telemetry),
        ]
        passed = all(rule["passed"] for rule in rules)
        checkpoint = connection.execute(
            "SELECT last_raw_record_id FROM fact_etl_checkpoint WHERE pipeline_name=?",
            ("raw_to_analysis_facts_v1",)).fetchone()
        return {
            "audited_at": datetime.now(timezone.utc).isoformat(),
            "quality_gate_passed": passed,
            "rules_checked": len(rules),
            "rules_failed": sum(not rule["passed"] for rule in rules),
            "raw_counts": raw_counts,
            "fact_counts": fact_counts,
            "fact_checkpoint": checkpoint[0] if checkpoint else None,
            "join_check": {"joined_rows": join["joined_rows"],
                           "distinct_tasks": join["distinct_tasks"],
                           "metric_rule": "一对多Join后的任务指标必须使用COUNT(DISTINCT task_id)"},
            "rules": rules,
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = audit_facts(args.database)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")
    if not report["quality_gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
