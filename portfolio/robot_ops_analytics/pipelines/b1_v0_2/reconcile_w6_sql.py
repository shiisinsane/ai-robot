#!/usr/bin/env python3
"""执行B1正式SQL，与独立Python统计对账，并生成跨版本并列摘要。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb

from portfolio.robot_ops_analytics.pipelines.b1_v0_2.analyze_w6_b1 import analyze


ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "sql/b1_v0_2"


def query(connection: duckdb.DuckDBPyConnection, path: Path) -> list[dict[str, Any]]:
    cursor = connection.execute(path.read_text(encoding="utf-8"))
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _close(left: float, right: float, tolerance: float = 1e-9) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def reconcile(b1_duckdb: Path, b1_sqlite: Path, legacy_duckdb: Path) -> dict[str, Any]:
    connection = duckdb.connect(str(b1_duckdb), read_only=True)
    try:
        legacy_path = str(legacy_duckdb.resolve()).replace("'", "''")
        connection.execute(f"ATTACH '{legacy_path}' AS legacy (READ_ONLY)")
        gate = query(connection, SQL_DIR / "00_data_contract_checks.sql")[0]
        if not gate["quality_gate_passed"]:
            raise ValueError(f"B1 SQL数据门禁失败：{gate}")
        kpis = query(connection, SQL_DIR / "01_obstacle_kpis.sql")
        features = query(connection, SQL_DIR / "02_task_telemetry_features.sql")
        guardrails = query(connection, SQL_DIR / "03_obstacle_guardrails.sql")
        cross_version = query(connection, SQL_DIR / "04_cross_version_comparison.sql")
    finally:
        connection.close()

    python_result = analyze(b1_sqlite)
    kpi_by_group = {row["obstacle_profile"]: row for row in kpis}
    guardrail_by_group = {row["obstacle_profile"]: row for row in guardrails}
    checks = []
    for group, expected in python_result["groups"].items():
        actual_kpi = kpi_by_group[group]
        actual_guardrail = guardrail_by_group[group]
        fields = {
            "valid_task_count": actual_kpi["task_count"],
            "success_count": actual_kpi["success_count"],
            "failure_count": actual_kpi["failure_count"],
            "failure_rate": actual_kpi["failure_rate"],
            "cycle_time_median_sec": actual_kpi["p50_cycle_time_sec"],
            "cycle_time_p90_sec": actual_kpi["p90_cycle_time_sec"],
            "cycle_time_p95_sec": actual_kpi["p95_cycle_time_sec"],
            "max_abs_lateral_deviation_median_m": actual_guardrail["p50_max_abs_lateral_deviation_m"],
            "max_abs_lateral_deviation_p90_m": actual_guardrail["p90_max_abs_lateral_deviation_m"],
            "minimum_obstacle_distance_observed_minimum_m": actual_guardrail["observed_minimum_obstacle_distance_m"],
            "safety_stop_task_rate": actual_guardrail["safety_stop_task_rate"],
            "stale_sensor_task_rate": actual_guardrail["stale_sensor_task_rate"],
            "valid_telemetry_coverage_rate": actual_guardrail["valid_telemetry_coverage_rate"],
        }
        for metric, actual in fields.items():
            passed = _close(actual, expected[metric])
            checks.append({"group": group, "metric": metric, "sql": actual,
                           "python": expected[metric], "passed": passed})

    return {
        "dataset_version": "roa-validation-b1-v0.2",
        "sql_gate": gate,
        "sql_python_reconciliation_passed": all(item["passed"] for item in checks),
        "reconciliation_checks": checks,
        "task_feature_rows": len(features),
        "cross_version_comparison_rule": "分别计算、并列解释；禁止混表总体估计",
        "cross_version_overall": cross_version,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b1-duckdb", type=Path, required=True)
    parser.add_argument("--b1-sqlite", type=Path, required=True)
    parser.add_argument("--legacy-duckdb", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = reconcile(args.b1_duckdb, args.b1_sqlite, args.legacy_duckdb)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"B1 SQL/Python对账：{result['sql_python_reconciliation_passed']}，检查={len(result['reconciliation_checks'])}")
    if not result["sql_python_reconciliation_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
