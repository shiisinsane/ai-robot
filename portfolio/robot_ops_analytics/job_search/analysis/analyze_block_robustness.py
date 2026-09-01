#!/usr/bin/env python3
"""对B1正式实验执行保留随机区组结构的事后稳健性分析。"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
from pathlib import Path
import random
from typing import Any

from portfolio.robot_ops_analytics.pipelines.b1_v0_2.analyze_w6_b1 import load_tasks, quantile


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = ROOT.parents[1] / "artifacts/roa_b1/roa-validation-b1-v0.2/etl/analysis.sqlite"
DEFAULT_PLAN = ROOT / "plans/b1_v0_2/w6_b1_formal_plan_v0.2.jsonl"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "results"
SEED = 20260901
RESAMPLES = 10_000
METRICS = ("cycle_time_sec", "max_abs_lateral_deviation_m")


def load_blocked_tasks(database: Path, plan_path: Path) -> list[dict[str, Any]]:
    tasks = load_tasks(database)
    plan = [json.loads(line) for line in plan_path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    blocks = {row["task_id"]: int(row["validation_block"]) for row in plan}
    if set(blocks) != {row["task_id"] for row in tasks}:
        raise ValueError("B1事实任务与冻结计划task_id不完全一致")
    rows = [{**row, "validation_block": blocks[row["task_id"]]} for row in tasks]
    validate_blocks(rows)
    return rows


def validate_blocks(rows: list[dict[str, Any]]) -> None:
    expected = {"none", "low", "medium"}
    block_ids = sorted({int(row["validation_block"]) for row in rows})
    if block_ids != list(range(1, 16)):
        raise ValueError(f"区组编号不完整：{block_ids}")
    for block_id in block_ids:
        profiles = [row["obstacle_profile"] for row in rows
                    if int(row["validation_block"]) == block_id]
        if len(profiles) != 3 or set(profiles) != expected:
            raise ValueError(f"区组{block_id}不是none/low/medium完整三臂：{profiles}")


def by_block(rows: list[dict[str, Any]]) -> dict[int, dict[str, dict[str, Any]]]:
    validate_blocks(rows)
    return {
        block_id: {
            row["obstacle_profile"]: row for row in rows
            if int(row["validation_block"]) == block_id
        }
        for block_id in range(1, 16)
    }


def marginal_median_difference(blocks: dict[int, dict[str, dict[str, Any]]],
                               block_sample: list[int], treatment: str,
                               metric: str) -> float:
    treatment_values = [float(blocks[block][treatment][metric]) for block in block_sample]
    control_values = [float(blocks[block]["none"][metric]) for block in block_sample]
    return quantile(treatment_values, .5) - quantile(control_values, .5)


def block_bootstrap(blocks: dict[int, dict[str, dict[str, Any]]], treatment: str,
                    metric: str, rng: random.Random, resamples: int = RESAMPLES) -> dict[str, Any]:
    block_ids = sorted(blocks)
    observed = marginal_median_difference(blocks, block_ids, treatment, metric)
    estimates = []
    for _ in range(resamples):
        sample = [rng.choice(block_ids) for _ in block_ids]
        estimates.append(marginal_median_difference(blocks, sample, treatment, metric))
    paired_differences = [
        float(blocks[block][treatment][metric]) - float(blocks[block]["none"][metric])
        for block in block_ids
    ]
    return {
        "estimate_marginal_median_difference": observed,
        "block_bootstrap_percentile_95": [quantile(estimates, .025), quantile(estimates, .975)],
        "paired_block_difference_median": quantile(paired_differences, .5),
        "paired_block_difference_min": min(paired_differences),
        "paired_block_difference_max": max(paired_differences),
        "block_count": len(block_ids),
        "bootstrap_resamples": resamples,
    }


def exact_paired_randomization_p(blocks: dict[int, dict[str, dict[str, Any]]],
                                 treatment: str, metric: str) -> float:
    """区组内交换处理标签，对边际中位数差执行精确双侧随机化检验。"""
    block_ids = sorted(blocks)
    pairs = [(float(blocks[block][treatment][metric]),
              float(blocks[block]["none"][metric])) for block in block_ids]
    observed = abs(quantile([pair[0] for pair in pairs], .5) -
                   quantile([pair[1] for pair in pairs], .5))
    extreme = 0
    total = 0
    for swaps in itertools.product((False, True), repeat=len(pairs)):
        treatment_values = [pair[1] if swap else pair[0] for pair, swap in zip(pairs, swaps)]
        control_values = [pair[0] if swap else pair[1] for pair, swap in zip(pairs, swaps)]
        statistic = abs(quantile(treatment_values, .5) - quantile(control_values, .5))
        extreme += statistic >= observed - 1e-12
        total += 1
    return extreme / total


def analyze(rows: list[dict[str, Any]], resamples: int = RESAMPLES,
            seed: int = SEED) -> dict[str, Any]:
    blocks = by_block(rows)
    rng = random.Random(seed)
    comparisons = {}
    for treatment in ("low", "medium"):
        metrics = {}
        for metric in METRICS:
            result = block_bootstrap(blocks, treatment, metric, rng, resamples)
            result["exact_paired_randomization_two_sided_p"] = exact_paired_randomization_p(
                blocks, treatment, metric)
            metrics[metric] = result
        comparisons[f"{treatment}_minus_none"] = metrics
    return {
        "analysis_type": "post_hoc_block_robustness",
        "primary_analysis_unchanged": True,
        "dataset_version": "roa-validation-b1-v0.2",
        "seed": seed,
        "comparisons": comparisons,
        "limitations": [
            "本分析为事后稳健性复核，不替代或冒充预注册主分析",
            "结果仅适用于冻结的单路线ROS 2/Gazebo仿真配置",
        ],
    }


def write_outputs(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "block_robustness.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = []
    for comparison, metrics in result["comparisons"].items():
        for metric, values in metrics.items():
            rows.append({
                "comparison": comparison,
                "metric": metric,
                "estimate": values["estimate_marginal_median_difference"],
                "ci95_low": values["block_bootstrap_percentile_95"][0],
                "ci95_high": values["block_bootstrap_percentile_95"][1],
                "paired_difference_median": values["paired_block_difference_median"],
                "randomization_p": values["exact_paired_randomization_two_sided_p"],
            })
    with (output_dir / "block_effects.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = analyze(load_blocked_tasks(args.database, args.plan))
    write_outputs(result, args.output_dir)
    print(json.dumps(result["comparisons"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
