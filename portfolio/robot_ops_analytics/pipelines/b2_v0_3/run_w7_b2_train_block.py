#!/usr/bin/env python3
"""预览或执行已授权的B2训练区组1；一次一槽位、失败即停。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

import yaml

from .write_pilot_obstacle_config import build as build_obstacle_config
from ..common.validate_w4_sample import validate


ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
CONFIG = ROOT / "config/w7_b2_preregistration_v0.3.yaml"
PLAN = ROOT / "plans/b2_v0_3/w7_b2_formal_plan_v0.3.jsonl"
SAFE_RUNNER = ROOT / "scripts/common/run_w4_safe_group.sh"
OUTPUT = REPO / "artifacts/roa_b2/roa-risk-b2-v0.3/train-block-01"


def rows():
    return [json.loads(line) for line in PLAN.read_text(encoding="utf-8").splitlines()]


def prior_counts(slot: int, state_path: Path) -> tuple[int, int, int]:
    if slot == 1:
        return 0, 0, 0
    if not state_path.is_file():
        raise ValueError("缺少前序有效槽位状态，拒绝推测滞后历史")
    state = [json.loads(line) for line in state_path.read_text(encoding="utf-8").splitlines()]
    if [row["plan_index"] for row in state] != list(range(1, slot)):
        raise ValueError("前序有效槽位不连续")
    window = state[-10:]
    failures = sum(row["terminal_status"] in {"failed", "timeout"} for row in window)
    timeouts = sum(row["terminal_status"] == "timeout" for row in window)
    return len(window), failures, timeouts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, required=True, choices=range(1, 46))
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--domain-id", type=int, default=160)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if not config.get("formal_collection_authorized") or config.get("authorization_scope") != \
            "train_block_01_only_slots_001_to_045":
        raise SystemExit("训练区组1未获得正式采集授权")
    task = next(row for row in rows() if row["plan_index"] == args.slot)
    if task["randomized_block"] != 1 or task["model_split"] != "train":
        raise SystemExit("请求槽位不属于已授权训练区组1")
    batch_id = f"b2-train-b01-slot-{args.slot:03d}-attempt-{args.attempt:03d}"
    batch_dir = OUTPUT / batch_id
    task_plan = batch_dir / "authorized-task.jsonl"
    obstacle = batch_dir / "config_runtime/obstacle.yaml"
    state_path = OUTPUT / "valid_slots.jsonl"
    counts = prior_counts(args.slot, state_path)
    completed = [] if not state_path.is_file() else [json.loads(line) for line in
                state_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.slot != len(completed) + 1:
        raise SystemExit(f"只能执行首个未完成槽位：{len(completed) + 1}")
    authorized = {**task, "environment_ready": True, "qualification_ready": True}
    command = ["bash", str(SAFE_RUNNER), "--batch-dir", str(batch_dir),
               "--domain-id", str(args.domain_id), "--partition", f"roa_b2_b01_s{args.slot:03d}_a{args.attempt:03d}",
               "--experiment-id", batch_id, "--plan", str(task_plan),
               "--environment-profile", task["environment_profile"],
               "--obstacle-profile", task["obstacle_profile"], "--obstacle-config", str(obstacle),
               "--initial-perturbation", task["initial_perturbation"],
               "--initial-pose", str(task["start_x"]), str(task["start_y"]), str(task["start_yaw"]),
               "--task-id", task["task_id"], "--continue-on-task-failure"]
    if args.slot == 1:
        command.append("--no-history")
    else:
        command += ["--prior-task-count-window-10", str(counts[0]),
                    "--prior-failure-count-window-10", str(counts[1]),
                    "--prior-timeout-count-window-10", str(counts[2])]
    print(f"槽位={args.slot}/45 task={task['task_id']} domain={args.domain_id} history={counts}")
    print(f"输出={batch_dir}")
    if not args.execute:
        print("当前仅预览；添加--execute后启动正式采集。")
        return 0
    if batch_dir.exists():
        raise SystemExit(f"输出目录已存在，拒绝覆盖：{batch_dir}")
    obstacle.parent.mkdir(parents=True)
    obstacle.write_text(yaml.safe_dump(build_obstacle_config(task, formal_ready=True), allow_unicode=True,
                                       sort_keys=False), encoding="utf-8")
    task_plan.write_text(json.dumps(authorized, ensure_ascii=False, sort_keys=True) + "\n",
                         encoding="utf-8")
    env = os.environ.copy(); env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    return_code = subprocess.run(command, cwd=REPO, env=env, check=False).returncode
    if return_code:
        return return_code
    validation = validate(batch_dir, task["task_id"])
    records = [json.loads(line) for line in
               (batch_dir / "structured/records.jsonl").read_text(encoding="utf-8").splitlines()]
    terminal = next(row for row in records if row.get("task_id") == task["task_id"] and
                    row.get("record_type") == "task_context" and row.get("event") == "terminal")
    status = "success" if validation == "valid_success" else (
        "timeout" if int(terminal.get("error_code", 0)) == 203 else "failed")
    with state_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"plan_index": args.slot, "task_id": task["task_id"],
                                 "batch_id": batch_id, "terminal_status": status,
                                 "validation": validation}, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"槽位{args.slot}已通过门禁：{validation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
