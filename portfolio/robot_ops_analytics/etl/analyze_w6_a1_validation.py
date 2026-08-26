#!/usr/bin/env python3
"""封板并分析W6 A1控制变量验证实验。"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [center - margin, center + margin]


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    row1, row2, col1 = a + b, c + d, a + c
    total = row1 + row2
    lo, hi = max(0, col1 - row2), min(row1, col1)

    def probability(x: int) -> float:
        return math.comb(col1, x) * math.comb(total - col1, row1 - x) / math.comb(total, row1)

    observed = probability(a)
    return min(1.0, sum(probability(x) for x in range(lo, hi + 1)
                        if probability(x) <= observed + 1e-15))


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def load_attempts(root: Path) -> list[dict[str, str]]:
    attempts = []
    for path in sorted(root.glob("a1-campaign-[0-9][0-9][0-9]-results.tsv")):
        with path.open(encoding="utf-8", newline="") as stream:
            attempts.extend(csv.DictReader(stream, delimiter="\t"))
    return attempts


def analyze(root: Path) -> dict:
    attempts = load_attempts(root)
    valid = [row for row in attempts if row["validation"].startswith("valid_")]
    by_task: dict[str, dict[str, str]] = {}
    for row in valid:
        if row["task_id"] in by_task:
            raise ValueError(f"任务存在多个有效样本：{row['task_id']}")
        by_task[row["task_id"]] = row
    if len(by_task) != 30:
        raise ValueError(f"有效任务数应为30，实际为{len(by_task)}")

    tasks = []
    for row in sorted(valid, key=lambda item: int(item["run_order"])):
        batch = root / row["batch_id"]
        records = [json.loads(line) for line in
                   (batch / "structured/records.jsonl").read_text(encoding="utf-8").splitlines()]
        contexts = [item for item in records if item.get("record_type") == "task_context"]
        terminals = [item for item in contexts if item.get("event") == "terminal"]
        accepted = [item for item in contexts if item.get("event") == "accepted"]
        telemetry = [item for item in records if item.get("record_type") == "task_telemetry_1s"]
        if len(terminals) != 1 or len(accepted) != 1 or not telemetry:
            raise ValueError(f"{row['task_id']}的终态、接受事件或遥测不唯一/缺失")
        terminal, accepted_at = terminals[0], accepted[0]["event_time_sim"]
        early = [item for item in telemetry
                 if item["bucket_end_sim"] > accepted_at
                 and item["bucket_start_sim"] < accepted_at + 3.0]
        task = {
            **row,
            "success": bool(terminal["success"]),
            "error_code": int(terminal["error_code"]),
            "action_status": int(terminal["action_status"]),
            "cycle_time_sec": terminal["event_time_sim"] - accepted_at,
            "early_3s_mean_abs_linear_speed_mps": (
                sum(abs(item["mean_linear_speed_mps"]) for item in early) / len(early)),
            "entered_sensing": any("进入到点感知" in item.get("message", "") for item in contexts),
            "minimum_obstacle_distance_m": min(item["minimum_valid_scan_range_m"] for item in telemetry),
            "safety_stop": any(item["safety_stop_active"] for item in telemetry),
            "stale_sensor": any(item["stale_sensor_mask"] != 0 for item in telemetry),
            "valid_telemetry_coverage_rate": sum(
                item["required_topics_present"] and item["timestamp_valid"] for item in telemetry
            ) / len(telemetry),
        }
        tasks.append(task)

    groups = {}
    for profile in ("low", "medium"):
        rows = [task for task in tasks if task["obstacle_profile"] == profile]
        failures = sum(not task["success"] for task in rows)
        code201 = sum(task["error_code"] == 201 for task in rows)
        cycles = [task["cycle_time_sec"] for task in rows]
        groups[profile] = {
            "task_count": len(rows), "success_count": len(rows) - failures,
            "failure_count": failures, "failure_rate": failures / len(rows),
            "failure_rate_wilson_95": wilson(failures, len(rows)),
            "error_code_201_count": code201, "error_code_201_rate": code201 / len(rows),
            "cycle_time_mean_sec": sum(cycles) / len(cycles),
            "cycle_time_p50_sec": quantile(cycles, .5),
            "cycle_time_p90_sec": quantile(cycles, .9),
            "cycle_time_p95_sec": quantile(cycles, .95),
            "early_3s_mean_abs_linear_speed_mps": sum(
                task["early_3s_mean_abs_linear_speed_mps"] for task in rows) / len(rows),
            "entered_sensing_count": sum(task["entered_sensing"] for task in rows),
            "minimum_obstacle_distance_m": min(task["minimum_obstacle_distance_m"] for task in rows),
            "safety_stop_task_count": sum(task["safety_stop"] for task in rows),
            "stale_sensor_task_count": sum(task["stale_sensor"] for task in rows),
            "valid_telemetry_coverage_rate": sum(
                task["valid_telemetry_coverage_rate"] for task in rows) / len(rows),
        }

    low, medium = groups["low"], groups["medium"]
    invalid = [row for row in attempts if row["validation"] == "invalid"]
    return {
        "dataset_version": "roa-validation-a1-v0.1",
        "valid_task_count": len(tasks), "invalid_attempt_count": len(invalid),
        "invalid_attempt_batch_ids": [row["batch_id"] for row in invalid],
        "groups": groups,
        "effects": {
            "failure_risk_difference_medium_minus_low": medium["failure_rate"] - low["failure_rate"],
            "failure_risk_ratio_medium_over_low": None if low["failure_rate"] == 0 else medium["failure_rate"] / low["failure_rate"],
            "fisher_exact_two_sided_p": fisher_two_sided(
                medium["failure_count"], medium["success_count"],
                low["failure_count"], low["success_count"]),
        },
        "tasks": tasks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.input_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"A1分析完成：有效任务={result['valid_task_count']}，无效尝试={result['invalid_attempt_count']}")


if __name__ == "__main__":
    main()
