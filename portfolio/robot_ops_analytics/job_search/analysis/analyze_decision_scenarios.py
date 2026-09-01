#!/usr/bin/env python3
"""按冻结合同执行任务预算、理论容量与改道时间情景分析。"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random
from statistics import mean
from typing import Any

from portfolio.robot_ops_analytics.job_search.analysis.analyze_block_robustness import (
    DEFAULT_DATABASE, DEFAULT_PLAN, SEED, analyze as analyze_block_robustness,
    by_block, load_blocked_tasks,
)
from portfolio.robot_ops_analytics.pipelines.b1_v0_2.analyze_w6_b1 import quantile


DEFAULT_OUTPUT = Path(__file__).resolve().parent / "results"
FIXED_BUDGETS = (30.0, 45.0, 60.0, 75.0, 90.0)
SEGMENTED_QUANTILES = (0.90, 0.95)
GROUPS = ("none", "low", "medium")
CAPACITY_SCENARIOS = {
    "simple_heavy": {"none": 0.70, "low": 0.20, "medium": 0.10},
    "balanced": {"none": 1 / 3, "low": 1 / 3, "medium": 1 / 3},
    "complex_heavy": {"none": 0.10, "low": 0.30, "medium": 0.60},
}
RESAMPLES = 10_000


def cross_validated_segmented_budgets(rows: list[dict[str, Any]], q: float) -> dict[str, float]:
    """用其余14个完整区组为每个留出任务估计分档预算。"""
    blocks = by_block(rows)
    budgets = {}
    for held_out in sorted(blocks):
        training_blocks = [block for block in blocks if block != held_out]
        for group in GROUPS:
            training = [float(blocks[block][group]["cycle_time_sec"])
                        for block in training_blocks]
            budgets[blocks[held_out][group]["task_id"]] = quantile(training, q)
    if len(budgets) != 45:
        raise ValueError(f"样本外预算数量错误：{len(budgets)}")
    return budgets


def summarize_policy(rows: list[dict[str, Any]], policy_id: str,
                     budgets: dict[str, float]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    details = []
    for row in rows:
        budget = float(budgets[row["task_id"]])
        cycle = float(row["cycle_time_sec"])
        details.append({
            "policy_id": policy_id,
            "task_id": row["task_id"],
            "validation_block": int(row["validation_block"]),
            "obstacle_profile": row["obstacle_profile"],
            "cycle_time_sec": cycle,
            "allocated_budget_sec": budget,
            "potential_false_escalation": int(cycle > budget),
            "budget_utilization": cycle / budget,
            "remaining_buffer_sec": budget - cycle,
        })
    summaries = []
    for group in ("overall", *GROUPS):
        selected = details if group == "overall" else [
            row for row in details if row["obstacle_profile"] == group]
        summaries.append({
            "policy_id": policy_id,
            "obstacle_profile": group,
            "task_count": len(selected),
            "potential_false_escalation_count": sum(
                row["potential_false_escalation"] for row in selected),
            "potential_false_escalation_rate": sum(
                row["potential_false_escalation"] for row in selected) / len(selected),
            "mean_allocated_budget_sec": mean(row["allocated_budget_sec"] for row in selected),
            "p90_allocated_budget_sec": quantile(
                [row["allocated_budget_sec"] for row in selected], .9),
            "median_budget_utilization": quantile(
                [row["budget_utilization"] for row in selected], .5),
            "p90_budget_utilization": quantile(
                [row["budget_utilization"] for row in selected], .9),
            "median_remaining_buffer_sec": quantile(
                [row["remaining_buffer_sec"] for row in selected], .5),
        })
    return summaries, details


def analyze_budget_policies(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]],
                                                                  list[dict[str, Any]]]:
    summaries, details = [], []
    for fixed in FIXED_BUDGETS:
        policy_id = f"fixed_{int(fixed)}s"
        budgets = {row["task_id"]: fixed for row in rows}
        policy_summary, policy_details = summarize_policy(rows, policy_id, budgets)
        summaries.extend(policy_summary)
        details.extend(policy_details)
    for q in SEGMENTED_QUANTILES:
        policy_id = f"segmented_lobo_p{int(q * 100)}"
        budgets = cross_validated_segmented_budgets(rows, q)
        policy_summary, policy_details = summarize_policy(rows, policy_id, budgets)
        summaries.extend(policy_summary)
        details.extend(policy_details)
    return summaries, details


def capacity_scenarios(rows: list[dict[str, Any]], seed: int = SEED,
                       resamples: int = RESAMPLES) -> list[dict[str, Any]]:
    blocks = by_block(rows)
    block_ids = sorted(blocks)
    rng = random.Random(seed)
    output = []
    for scenario, weights in CAPACITY_SCENARIOS.items():
        group_means = {
            group: mean(float(blocks[block][group]["cycle_time_sec"]) for block in block_ids)
            for group in GROUPS
        }
        weighted_cycle = sum(weights[group] * group_means[group] for group in GROUPS)
        estimates = []
        for _ in range(resamples):
            sample = [rng.choice(block_ids) for _ in block_ids]
            sampled_means = {
                group: mean(float(blocks[block][group]["cycle_time_sec"]) for block in sample)
                for group in GROUPS
            }
            cycle = sum(weights[group] * sampled_means[group] for group in GROUPS)
            estimates.append(3600 / cycle)
        output.append({
            "scenario": scenario,
            "none_share": weights["none"],
            "low_share": weights["low"],
            "medium_share": weights["medium"],
            "weighted_mean_cycle_time_sec": weighted_cycle,
            "theoretical_tasks_per_hour": 3600 / weighted_cycle,
            "block_bootstrap_95_low": quantile(estimates, .025),
            "block_bootstrap_95_high": quantile(estimates, .975),
            "bootstrap_resamples": resamples,
        })
    return output


def reroute_break_even(rows: list[dict[str, Any]]) -> dict[str, Any]:
    robust = analyze_block_robustness(rows)
    output = {
        "interpretation": "备选路线额外时间低于该绕行代价时，改道才具有时间上的候选价值",
        "not_an_automatic_reroute_rule": True,
        "comparisons": {},
    }
    for treatment in ("low", "medium"):
        result = robust["comparisons"][f"{treatment}_minus_none"]["cycle_time_sec"]
        output["comparisons"][f"{treatment}_minus_none"] = {
            "marginal_median_penalty_sec": result["estimate_marginal_median_difference"],
            "block_bootstrap_95": result["block_bootstrap_percentile_95"],
            "paired_block_penalty_median_sec": result["paired_block_difference_median"],
            "paired_block_penalty_min_sec": result["paired_block_difference_min"],
            "paired_block_penalty_max_sec": result["paired_block_difference_max"],
        }
    return output


def guardrails(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "task_count": len(rows),
        "safety_stop_task_count": sum(bool(row["safety_stop"]) for row in rows),
        "stale_sensor_task_count": sum(bool(row["stale_sensor"]) for row in rows),
        "mean_valid_telemetry_coverage_rate": mean(
            float(row["valid_telemetry_coverage_rate"]) for row in rows),
        "formal_visual_collision_count": 0,
        "scope_note": "护栏描述原B1数据；预算策略未实际执行，不能声称策略保持安全",
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rows = load_blocked_tasks(args.database, args.plan)
    summaries, details = analyze_budget_policies(rows)
    capacities = capacity_scenarios(rows)
    reroute = reroute_break_even(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "budget_policy_results.csv", summaries)
    write_csv(args.output_dir / "budget_policy_task_details.csv", details)
    write_csv(args.output_dir / "capacity_scenarios.csv", capacities)
    (args.output_dir / "reroute_break_even.json").write_text(
        json.dumps(reroute, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "decision_analysis_summary.json").write_text(json.dumps({
        "analysis_type": "post_hoc_simulation_decision_scenarios",
        "dataset_version": "roa-validation-b1-v0.2",
        "budget_policy_overall": [row for row in summaries
                                  if row["obstacle_profile"] == "overall"],
        "capacity_scenarios": capacities,
        "reroute_break_even": reroute,
        "guardrails": guardrails(rows),
        "limitations": [
            "候选预算不是正式SLA",
            "全部B1任务最终成功，不能估计失败召回率或异常检测延迟",
            "容量和改道结果为单路线仿真情景，不是生产收益",
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"policies": [row for row in summaries
                                   if row["obstacle_profile"] == "overall"],
                      "capacities": capacities, "guardrails": guardrails(rows)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
