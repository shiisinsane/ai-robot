#!/usr/bin/env python3
"""从冻结计划安全预览或执行一个W7 B2 GUI诊断Pilot。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

import yaml

from .write_pilot_obstacle_config import build as build_obstacle_config


PORTFOLIO_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PORTFOLIO_ROOT.parents[1]
DEFAULT_PLAN = PORTFOLIO_ROOT / "plans/b2_v0_3/w7_b2_qualification_plan_v0.1.jsonl"
SAFE_RUNNER = PORTFOLIO_ROOT / "scripts/common/run_w4_safe_group.sh"
RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,39}$")


def load_tasks(plan: Path) -> list[dict]:
    return [json.loads(line) for line in plan.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def select_task(plan: Path, task_id: str) -> dict:
    matches = [row for row in load_tasks(plan) if row["task_id"] == task_id]
    if len(matches) != 1:
        raise ValueError(f"冻结计划中task-id不存在或不唯一：{task_id}")
    return matches[0]


def build_run(task: dict, plan: Path, run_id: str, domain_id: int | None = None):
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run-id只能使用3～40位小写字母、数字、下划线或连字符")
    selected_domain = int(task["ros_domain_id"] if domain_id is None else domain_id)
    if not 0 <= selected_domain <= 232:
        raise ValueError("domain-id必须在0～232之间")
    batch_dir = REPO_ROOT / "artifacts/roa_b2" / run_id
    obstacle_config = batch_dir / "config_runtime/obstacle.yaml"
    partition = f"roa_b2_{run_id}"
    if len(partition) > 64:
        raise ValueError("run-id生成的Gazebo分区超过64字符")
    command = [
        "bash", str(SAFE_RUNNER),
        "--batch-dir", str(batch_dir),
        "--domain-id", str(selected_domain),
        "--partition", partition,
        "--experiment-id", f"roa-b2-{run_id}",
        "--plan", str(plan),
        "--environment-profile", task["environment_profile"],
        "--obstacle-profile", task["obstacle_profile"],
        "--obstacle-config", str(obstacle_config),
        "--initial-perturbation", task["initial_perturbation"],
        "--initial-pose", str(task["start_x"]), str(task["start_y"]),
        str(task["start_yaw"]),
        "--task-id", task["task_id"],
        "--qualification-pilot", "--gui", "--no-history",
    ]
    return batch_dir, obstacle_config, selected_domain, partition, command


def show_tasks(tasks: list[dict]) -> None:
    for task in tasks:
        print(f"{task['qualification_sequence']:>2}. {task['task_id']:<42} "
              f"路线={task['route_id']:<20} 障碍={task['obstacle_profile']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="列出15个可选task-id后退出")
    parser.add_argument("--task-id", help="从冻结计划选择一个任务")
    parser.add_argument("--run-id", help="本轮唯一名称，例如manual_diagnostic_003")
    parser.add_argument("--domain-id", type=int, help="可选；默认使用计划候选域")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN,
                        help="通常无需修改；默认使用正式冻结资格计划")
    parser.add_argument("--execute", action="store_true",
                        help="真正启动Gazebo GUI；省略时只预览自动解析结果")
    args = parser.parse_args()
    plan = args.plan.resolve()
    tasks = load_tasks(plan)
    if args.list:
        show_tasks(tasks)
        return 0
    if not args.task_id or not args.run_id:
        parser.error("除--list外，必须同时提供--task-id和--run-id")
    task = select_task(plan, args.task_id)
    batch_dir, obstacle_path, domain_id, partition, command = build_run(
        task, plan, args.run_id, args.domain_id)
    print(f"任务：{task['task_id']}")
    print(f"起点：({task['start_x']}, {task['start_y']}, {task['start_yaw']})")
    print(f"终点：({task['target_x']}, {task['target_y']}, {task['target_yaw']})")
    print(f"障碍：{task['obstacle_profile']} @ {task['obstacle_position']}")
    print(f"ROS域：{domain_id}；Gazebo分区：{partition}")
    print(f"输出：{batch_dir}")
    if not args.execute:
        print("当前仅预览；确认后添加 --execute 才会启动GUI。")
        return 0
    if batch_dir.exists():
        raise SystemExit(f"输出目录已经存在，拒绝覆盖；请更换run-id：{batch_dir}")
    obstacle_path.parent.mkdir(parents=True)
    obstacle_path.write_text(yaml.safe_dump(
        build_obstacle_config(task), allow_unicode=True, sort_keys=False), encoding="utf-8")
    environment = os.environ.copy()
    environment["LIBGL_ALWAYS_SOFTWARE"] = "1"
    return subprocess.run(command, cwd=REPO_ROOT, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
