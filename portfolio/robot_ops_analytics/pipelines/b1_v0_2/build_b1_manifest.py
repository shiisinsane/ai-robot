"""由B1正式活动日志生成严格白名单，隔离重试失败与旧版数据。"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from portfolio.robot_ops_analytics.pipelines.common.audit_baseline import audit_batch


EXPECTED_VERSION = "roa-validation-b1-v0.2"
EXPECTED_TASKS = {f"b1-formal-{index:04d}" for index in range(1, 46)}


def build_manifest(dataset_root: Path) -> dict[str, Any]:
    campaign_rows: list[dict[str, str]] = []
    for path in sorted(dataset_root.glob("b1-campaign-*-results.tsv")):
        if "preview" in path.name:
            continue
        with path.open(encoding="utf-8", newline="") as stream:
            campaign_rows.extend(csv.DictReader(stream, delimiter="\t"))

    selected = [row for row in campaign_rows if row.get("validation") == "valid_success"]
    task_counts = Counter(row.get("task_id") for row in selected)
    failures: list[str] = []
    if set(task_counts) != EXPECTED_TASKS:
        failures.append("正式任务集合不是预注册的45项")
    duplicates = sorted(task for task, count in task_counts.items() if count != 1)
    if duplicates:
        failures.append(f"正式任务出现重复有效记录：{duplicates}")

    tasks: list[dict[str, Any]] = []
    for campaign_row in sorted(selected, key=lambda row: int(row["run_order"])):
        batch_dir = dataset_root / campaign_row["batch_id"]
        try:
            audited = audit_batch(batch_dir)
        except (ValueError, OSError, json.JSONDecodeError) as error:
            failures.append(f"{batch_dir.name}：{error}")
            continue
        matches = [row for row in audited if row["task_id"] == campaign_row["task_id"]]
        if len(matches) != 1:
            failures.append(f"{batch_dir.name}与活动日志任务不一致")
            continue
        run_path = batch_dir / "batch_runner/run_results.jsonl"
        run = json.loads(run_path.read_text(encoding="utf-8").strip())
        if run.get("dataset_version") != EXPECTED_VERSION:
            failures.append(f"{batch_dir.name}数据版本不符")
            continue
        task = matches[0]
        task.update({
            "run_order": int(campaign_row["run_order"]),
            "validation_block": int(campaign_row["block"]),
            "dataset_version": EXPECTED_VERSION,
        })
        tasks.append(task)

    obstacle_counts = Counter(row["obstacle_profile"] for row in tasks)
    if obstacle_counts != Counter({"none": 15, "low": 15, "medium": 15}):
        failures.append(f"障碍分层不是每组15项：{dict(obstacle_counts)}")
    if len({row["batch_id"] for row in tasks}) != len(tasks):
        failures.append("有效任务未映射到唯一批次")

    return {
        "dataset_version": EXPECTED_VERSION,
        "source_root": str(dataset_root.resolve()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection_rule": "非preview活动日志中validation=valid_success，且通过批次审计",
        "quality_gate_passed": not failures and len(tasks) == 45,
        "counts": {
            "valid_tasks": len(tasks),
            "success_tasks": sum(row["terminal_status"] == "success" for row in tasks),
            "excluded_attempts": len(campaign_rows) - len(selected),
            "telemetry_buckets": sum(row["telemetry_bucket_count"] for row in tasks),
        },
        "distribution": {"obstacle": dict(sorted(obstacle_counts.items()))},
        "quality_failures": failures,
        "tasks": tasks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_manifest(args.dataset_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"quality_gate_passed": report["quality_gate_passed"],
                      **report["counts"], "obstacle": report["distribution"]["obstacle"]},
                     ensure_ascii=False, sort_keys=True))
    if not report["quality_gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
