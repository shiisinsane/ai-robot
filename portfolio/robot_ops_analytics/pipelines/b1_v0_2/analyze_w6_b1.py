#!/usr/bin/env python3
"""按B1预注册口径完成描述统计、Fisher检验和bootstrap区间。"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import random
import sqlite3
from typing import Any


DATASET_VERSION = "roa-validation-b1-v0.2"
GROUPS = ("none", "low", "medium")
SEED = 20260827
RESAMPLES = 10_000


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


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


def bootstrap_median_difference(treatment: list[float], control: list[float],
                                rng: random.Random, resamples: int = RESAMPLES) -> dict[str, Any]:
    observed = quantile(treatment, .5) - quantile(control, .5)
    estimates = []
    for _ in range(resamples):
        sampled_treatment = [rng.choice(treatment) for _ in treatment]
        sampled_control = [rng.choice(control) for _ in control]
        estimates.append(quantile(sampled_treatment, .5) - quantile(sampled_control, .5))
    return {
        "estimate": observed,
        "bootstrap_percentile_95": [quantile(estimates, .025), quantile(estimates, .975)],
        "bootstrap_resamples": resamples,
    }


def load_tasks(database: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        versions = {row[0] for row in connection.execute(
            "SELECT DISTINCT dataset_version FROM fact_task_execution")}
        if versions != {DATASET_VERSION}:
            raise ValueError(f"分析库数据版本不唯一或不正确：{sorted(versions)}")
        rows = connection.execute(
            """SELECT task_id, obstacle_profile, success, cycle_time_sec,
                      minimum_obstacle_distance_m, data_quality_valid
               FROM fact_task_execution ORDER BY task_id""").fetchall()
        tasks = []
        for row in rows:
            telemetry = connection.execute(
                """SELECT pose_y_m, safety_stop_active, stale_sensor_mask,
                          required_topics_present, timestamp_valid
                   FROM fact_task_telemetry_1s WHERE task_id=?""", (row["task_id"],)).fetchall()
            pose_y = [abs(item["pose_y_m"]) for item in telemetry if item["pose_y_m"] is not None]
            if not telemetry or not pose_y:
                raise ValueError(f"{row['task_id']}缺少B1分析所需遥测")
            tasks.append({
                **dict(row),
                "success": bool(row["success"]),
                "data_quality_valid": bool(row["data_quality_valid"]),
                "max_abs_lateral_deviation_m": max(pose_y),
                "safety_stop": any(bool(item["safety_stop_active"]) for item in telemetry),
                "stale_sensor": any((item["stale_sensor_mask"] or 0) != 0 for item in telemetry),
                "valid_telemetry_coverage_rate": sum(
                    bool(item["required_topics_present"]) and bool(item["timestamp_valid"])
                    for item in telemetry) / len(telemetry),
            })
        return tasks
    finally:
        connection.close()


def analyze(database: Path) -> dict[str, Any]:
    tasks = load_tasks(database)
    counts = {group: sum(task["obstacle_profile"] == group for task in tasks) for group in GROUPS}
    if len(tasks) != 45 or counts != {group: 15 for group in GROUPS}:
        raise ValueError(f"B1样本门禁失败：total={len(tasks)}, groups={counts}")
    if not all(task["data_quality_valid"] for task in tasks):
        raise ValueError("存在未通过质量门禁的任务")

    grouped = {group: [task for task in tasks if task["obstacle_profile"] == group]
               for group in GROUPS}
    summaries = {}
    for group, rows in grouped.items():
        failures = sum(not row["success"] for row in rows)
        cycles = [row["cycle_time_sec"] for row in rows]
        lateral = [row["max_abs_lateral_deviation_m"] for row in rows]
        summaries[group] = {
            "valid_task_count": len(rows),
            "success_count": len(rows) - failures,
            "failure_count": failures,
            "failure_rate": failures / len(rows),
            "failure_rate_wilson_95": wilson(failures, len(rows)),
            "cycle_time_median_sec": quantile(cycles, .5),
            "cycle_time_p90_sec": quantile(cycles, .9),
            "cycle_time_p95_sec": quantile(cycles, .95),
            "max_abs_lateral_deviation_median_m": quantile(lateral, .5),
            "max_abs_lateral_deviation_p90_m": quantile(lateral, .9),
            "minimum_obstacle_distance_observed_minimum_m": min(
                row["minimum_obstacle_distance_m"] for row in rows),
            "safety_stop_task_rate": sum(row["safety_stop"] for row in rows) / len(rows),
            "stale_sensor_task_rate": sum(row["stale_sensor"] for row in rows) / len(rows),
            "valid_telemetry_coverage_rate": sum(
                row["valid_telemetry_coverage_rate"] for row in rows) / len(rows),
        }

    rng = random.Random(SEED)
    comparisons = {}
    for treatment in ("low", "medium"):
        treatment_rows, control_rows = grouped[treatment], grouped["none"]
        failures_t = sum(not row["success"] for row in treatment_rows)
        failures_c = sum(not row["success"] for row in control_rows)
        comparisons[f"{treatment}_minus_none"] = {
            "failure_risk_difference": failures_t / 15 - failures_c / 15,
            "fisher_exact_two_sided_p": fisher_two_sided(
                failures_t, 15 - failures_t, failures_c, 15 - failures_c),
            "median_cycle_time_difference_sec": bootstrap_median_difference(
                [row["cycle_time_sec"] for row in treatment_rows],
                [row["cycle_time_sec"] for row in control_rows], rng),
            "median_max_abs_lateral_deviation_difference_m": bootstrap_median_difference(
                [row["max_abs_lateral_deviation_m"] for row in treatment_rows],
                [row["max_abs_lateral_deviation_m"] for row in control_rows], rng),
        }
    return {
        "dataset_version": DATASET_VERSION,
        "analysis_contract": "roa-w6-b1-preregistration-v0.2",
        "bootstrap_seed": SEED,
        "multiplicity_note": "全部比较透明报告，不主张家族错误率控制后的确证性结论",
        "groups": summaries,
        "comparisons": comparisons,
        "guardrails": {
            "formal_visual_collision_count": 0,
            "formal_visual_collision_source": "用户GUI人工确认",
        },
        "tasks": tasks,
    }


def write_csvs(result: dict[str, Any], output_dir: Path) -> None:
    with (output_dir / "b1_group_summary.csv").open("w", encoding="utf-8", newline="") as stream:
        rows = [{"obstacle_profile": group, **values} for group, values in result["groups"].items()]
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value) if isinstance(value, list) else value
                             for key, value in row.items()})
    with (output_dir / "b1_comparisons.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = ["comparison", "metric", "estimate", "ci95_low", "ci95_high", "fisher_p"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for comparison, values in result["comparisons"].items():
            for metric in ("median_cycle_time_difference_sec",
                           "median_max_abs_lateral_deviation_difference_m"):
                effect = values[metric]
                writer.writerow({"comparison": comparison, "metric": metric,
                                 "estimate": effect["estimate"],
                                 "ci95_low": effect["bootstrap_percentile_95"][0],
                                 "ci95_high": effect["bootstrap_percentile_95"][1],
                                 "fisher_p": values["fisher_exact_two_sided_p"]})


def write_svg(result: dict[str, Any], path: Path) -> None:
    panels = [
        ("median_cycle_time_difference_sec", "任务周期中位数差（秒）"),
        ("median_max_abs_lateral_deviation_difference_m", "最大横向偏移中位数差（米）"),
    ]
    width, height = 900, 460
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<text x="450" y="28" text-anchor="middle" font-family="sans-serif" font-size="20">B1相对none组的预注册效应与bootstrap 95%区间</text>']
    for panel_index, (metric, title) in enumerate(panels):
        x0 = 70 + panel_index * 440
        effects = [result["comparisons"][f"{group}_minus_none"][metric]
                   for group in ("low", "medium")]
        all_values = [value for effect in effects for value in
                      [effect["bootstrap_percentile_95"][0], effect["bootstrap_percentile_95"][1], 0]]
        lo, hi = min(all_values), max(all_values)
        padding = max((hi - lo) * .15, .01)
        lo, hi = lo - padding, hi + padding
        scale = lambda value: x0 + (value - lo) / (hi - lo) * 330
        svg.append(f'<text x="{x0 + 165}" y="65" text-anchor="middle" font-family="sans-serif" font-size="15">{title}</text>')
        svg.append(f'<line x1="{scale(0):.1f}" y1="85" x2="{scale(0):.1f}" y2="315" stroke="#999" stroke-dasharray="4 4"/>')
        for index, (group, effect) in enumerate(zip(("low", "medium"), effects)):
            y = 140 + index * 100
            ci = effect["bootstrap_percentile_95"]
            svg.extend([
                f'<text x="{x0 - 10}" y="{y + 5}" text-anchor="end" font-family="sans-serif" font-size="14">{group}</text>',
                f'<line x1="{scale(ci[0]):.1f}" y1="{y}" x2="{scale(ci[1]):.1f}" y2="{y}" stroke="#2563eb" stroke-width="4"/>',
                f'<circle cx="{scale(effect["estimate"]):.1f}" cy="{y}" r="7" fill="#dc2626"/>',
                f'<text x="{scale(effect["estimate"]):.1f}" y="{y - 14}" text-anchor="middle" font-family="sans-serif" font-size="12">{effect["estimate"]:.3f}</text>',
            ])
        svg.extend([
            f'<line x1="{x0}" y1="315" x2="{x0 + 330}" y2="315" stroke="black"/>',
            f'<text x="{x0}" y="340" text-anchor="middle" font-family="sans-serif" font-size="12">{lo:.2f}</text>',
            f'<text x="{x0 + 330}" y="340" text-anchor="middle" font-family="sans-serif" font-size="12">{hi:.2f}</text>',
        ])
    svg.append('<text x="450" y="420" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#555">红点：观测中位数差；蓝线：10,000次非参数bootstrap百分位95%区间</text>')
    svg.append('</svg>')
    path.write_text("\n".join(svg) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.database)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "b1_bootstrap_analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csvs(result, args.output_dir)
    write_svg(result, args.output_dir / "b1_bootstrap_effects.svg")
    print(f"B1统计完成：任务={sum(v['valid_task_count'] for v in result['groups'].values())}，bootstrap={RESAMPLES}")


if __name__ == "__main__":
    main()
