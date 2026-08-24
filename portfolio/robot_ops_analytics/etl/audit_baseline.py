"""审计W4正式批次并生成W5基线数据集清单。"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import yaml


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"缺少或为空：{path}")
    return [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines() if line.strip()]


def audit_batch(batch_dir: Path) -> list[dict[str, Any]]:
    results = _jsonl(batch_dir / "batch_runner/run_results.jsonl")
    indexed = Counter(result.get("task_id") for result in results)
    duplicate_index = sorted(task for task, count in indexed.items() if count != 1)
    if duplicate_index:
        raise ValueError(f"{batch_dir.name}运行索引任务不唯一：{duplicate_index}")
    records = _jsonl(batch_dir / "structured/records.jsonl")
    residue = batch_dir / "process/residue_check.txt"
    if "本批进程组残留检查：通过" not in residue.read_text(encoding="utf-8"):
        raise ValueError(f"{batch_dir.name}无残留门禁未通过")
    metadata_path = batch_dir / "rosbag/w4_pilot_bag/metadata.yaml"
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    message_count = int(metadata.get("rosbag2_bagfile_information", {}).get(
        "message_count", 0))
    if message_count <= 0:
        raise ValueError(f"{batch_dir.name} rosbag消息数无效")
    if not any(path.stat().st_size > 0 for path in
               (batch_dir / "rosbag/w4_pilot_bag").glob("*.db3")):
        raise ValueError(f"{batch_dir.name} rosbag数据库缺失")
    audited = []
    for result in results:
        task_id = result.get("task_id")
        terminals = [row for row in records if row.get("task_id") == task_id and
                     row.get("record_type") == "task_context" and
                     row.get("event") == "terminal"]
        telemetry = [row for row in records if row.get("task_id") == task_id and
                     row.get("record_type") == "task_telemetry_1s"]
        if len(terminals) != 1:
            raise ValueError(f"{task_id}终态数量不是1：{len(terminals)}")
        if not telemetry:
            raise ValueError(f"{task_id}没有任务遥测")
        if not all(row.get("required_topics_present") and row.get("timestamp_valid")
                   for row in telemetry):
            raise ValueError(f"{task_id}存在不完整或时间戳无效遥测")
        buckets = [row["bucket_start_sim"] for row in telemetry]
        if len(buckets) != len(set(buckets)):
            raise ValueError(f"{task_id}存在重复遥测桶")
        terminal = terminals[0]
        success = bool(terminal.get("success"))
        if result.get("return_code") != (0 if success else 1):
            raise ValueError(f"{task_id}Runner返回码与终态不一致")
        audited.append({
            "batch_id": batch_dir.name,
            "task_id": task_id,
            "experiment_id": result.get("experiment_id"),
            "run_origin": result.get("run_origin"),
            "route_id": result.get("route_id"),
            "obstacle_profile": result.get("obstacle_profile"),
            "initial_perturbation": result.get("initial_perturbation"),
            "parameter_profile": result.get("parameter_profile"),
            "repetition": result.get("repetition"),
            "terminal_status": "success" if success else "failed",
            "action_status": terminal.get("action_status"),
            "error_code": terminal.get("error_code"),
            "telemetry_bucket_count": len(telemetry),
            "rosbag_message_count": message_count,
        })
    return audited


def audit_dataset(dataset_root: Path, dataset_version: str) -> dict[str, Any]:
    rows = []
    failures = []
    for batch_dir in sorted(path for path in dataset_root.iterdir() if path.is_dir()):
        if not (batch_dir / "batch_runner/run_results.jsonl").exists():
            continue
        try:
            rows.extend(audit_batch(batch_dir))
        except (ValueError, json.JSONDecodeError, yaml.YAMLError, OSError) as error:
            failures.append({"batch_id": batch_dir.name, "reason": str(error)})
    task_counts = Counter(row["task_id"] for row in rows)
    duplicates = sorted(task for task, count in task_counts.items() if count > 1)
    if duplicates:
        failures.append({"batch_id": None, "reason": f"重复任务ID：{duplicates}"})
    valid_rows = [row for row in rows if row["task_id"] not in duplicates]
    return {
        "dataset_version": dataset_version,
        "source_root": str(dataset_root.resolve()),
        "quality_gate_passed": not failures,
        "counts": {
            "valid_tasks": len(valid_rows),
            "success_tasks": sum(row["terminal_status"] == "success" for row in valid_rows),
            "failed_tasks": sum(row["terminal_status"] == "failed" for row in valid_rows),
            "natural_tasks": sum(row["run_origin"] == "natural" for row in valid_rows),
            "fault_injection_tasks": sum(
                row["run_origin"] == "fault_injection" for row in valid_rows),
            "telemetry_buckets": sum(row["telemetry_bucket_count"] for row in valid_rows),
            "invalid_batches": len(failures),
        },
        "distribution": {
            "route": dict(sorted(Counter(row["route_id"] for row in valid_rows).items())),
            "obstacle": dict(sorted(Counter(
                row["obstacle_profile"] for row in valid_rows).items())),
            "initial_perturbation": dict(sorted(Counter(
                row["initial_perturbation"] for row in valid_rows).items())),
            "parameter_profile": dict(sorted(Counter(
                row["parameter_profile"] for row in valid_rows).items())),
        },
        "quality_failures": failures,
        "tasks": valid_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--dataset-version", default="roa-data-v0.1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_dataset(args.dataset_root, args.dataset_version)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))
    if not report["quality_gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
