#!/usr/bin/env python3
"""预览或由用户手动启动已授权的W7 B2第2项资格重跑。"""

import argparse
import os
from pathlib import Path
import subprocess

import yaml

from .run_w7_b2_diagnostic import DEFAULT_PLAN, REPO_ROOT, build_run, select_task
from .write_pilot_obstacle_config import build as build_obstacle_config


CONFIG = Path(__file__).resolve().parents[2] / "config/w7_b2_qualification_v0.1.yaml"
DATASET_ROOT = REPO_ROOT / "artifacts/roa_b2/roa-risk-b2-qualification-v0.3"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retry", type=int, required=True, help="本任务重跑序号，从1开始")
    parser.add_argument("--execute", action="store_true", help="由用户确认后真正启动GUI")
    args = parser.parse_args()
    if args.retry < 1:
        parser.error("--retry必须大于等于1")
    qualification = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if (qualification.get("status") != "pilot_rerun_authorized" or
            not qualification.get("pilot_execution_authorized")):
        raise SystemExit("第2项资格重跑未授权")
    task_id = qualification["rerun_task_id"]
    task = select_task(DEFAULT_PLAN, task_id)
    batch_name = f"b2-pilot-02-horizontal-center-low-retry-{args.retry:03d}"
    # 复用统一参数派生，随后把诊断输出根替换为资格数据集根。
    _, _, domain_id, partition, command = build_run(
        task, DEFAULT_PLAN, f"qual02_retry_{args.retry:03d}", int(task["ros_domain_id"]))
    batch_dir = DATASET_ROOT / batch_name
    obstacle_path = batch_dir / "config_runtime/obstacle.yaml"
    for flag, value in (("--batch-dir", str(batch_dir)),
                        ("--obstacle-config", str(obstacle_path)),
                        ("--experiment-id", f"roa-b2-qualification-02-retry-{args.retry:03d}")):
        command[command.index(flag) + 1] = value
    print(f"资格重跑：第2项，retry-{args.retry:03d}")
    print(f"任务：{task_id}")
    print(f"起点：({task['start_x']}, {task['start_y']}, {task['start_yaw']})")
    print(f"终点：({task['target_x']}, {task['target_y']}, {task['target_yaw']})")
    print(f"障碍：{task['obstacle_profile']} @ {task['obstacle_position']}")
    print(f"ROS域：{domain_id}；Gazebo分区：{partition}")
    print(f"输出：{batch_dir}")
    if not args.execute:
        print("当前仅预览；由用户确认后添加 --execute 才会启动GUI。")
        return 0
    if batch_dir.exists():
        raise SystemExit(f"输出目录已经存在，拒绝覆盖：{batch_dir}")
    obstacle_path.parent.mkdir(parents=True)
    obstacle_path.write_text(yaml.safe_dump(
        build_obstacle_config(task), allow_unicode=True, sort_keys=False), encoding="utf-8")
    environment = os.environ.copy()
    environment["LIBGL_ALWAYS_SOFTWARE"] = "1"
    return subprocess.run(command, cwd=REPO_ROOT, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
