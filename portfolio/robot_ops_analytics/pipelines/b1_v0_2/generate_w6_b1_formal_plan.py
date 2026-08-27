"""从冻结的B1预注册配置生成45槽位计划；不启动ROS或Gazebo。"""

import argparse
import hashlib
import json
from pathlib import Path
import random

import yaml


DEFAULT_CONFIG = Path(__file__).parents[2] / "config/w6_b1_preregistration_v0.2.yaml"


def generate(config):
    if config["status"] != "frozen_before_execution":
        raise ValueError("B1预注册配置未冻结")
    fixed = config["fixed_conditions"]
    groups = config["groups"]
    rng = random.Random(int(config["assignment"]["seed"]))
    rows = []
    for block in range(1, int(config["assignment"]["block_count"]) + 1):
        order = list(groups)
        rng.shuffle(order)
        for position, profile in enumerate(order, 1):
            index = len(rows) + 1
            obstacle = groups[profile]["obstacle_position"]
            rows.append({
                "plan_index": index,
                "task_id": f"b1-formal-{index:04d}",
                "campaign": "w6_b1_formal_validation",
                "dataset_version": config["dataset_version"],
                "environment_profile": f"natural__{profile}__none__baseline",
                "environment_ready": bool(config["formal_execution_authorized"]),
                "qualification_ready": False,
                "route_id": fixed["route_id"],
                "start_x": float(fixed["start_pose"]["x_m"]),
                "start_y": float(fixed["start_pose"]["y_m"]),
                "start_yaw": float(fixed["start_pose"]["yaw_rad"]),
                "target_x": float(fixed["target_pose"]["x_m"]),
                "target_y": float(fixed["target_pose"]["y_m"]),
                "target_yaw": float(fixed["target_pose"]["yaw_rad"]),
                "timeout_sec": float(fixed["task_timeout_sec"]),
                "obstacle_profile": profile,
                "obstacle_position": obstacle,
                "initial_perturbation": "none",
                "parameter_profile": "baseline",
                "validation_block": block,
                "repetition": block,
                "block_position": position,
                "assignment_seed": int(config["assignment"]["seed"]),
                "requires_fresh_environment": True,
            })
    expected = sum(int(group["required_valid_tasks"]) for group in groups.values())
    if len(rows) != expected or len({row["task_id"] for row in rows}) != expected:
        raise ValueError("B1正式计划数量或任务ID错误")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    try:
        rows = generate(config)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    print(f"B1正式计划已生成：{len(rows)}项；SHA-256={hashlib.sha256(payload.encode()).hexdigest()}；未启动ROS/Gazebo")


if __name__ == "__main__":
    main()
