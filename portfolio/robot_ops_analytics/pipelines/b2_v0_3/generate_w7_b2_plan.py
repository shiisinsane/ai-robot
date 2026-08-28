#!/usr/bin/env python3
"""生成B2候选完整随机区组计划；只生成文件，不启动ROS或Gazebo。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config/w7_b2_design_draft_v0.1.yaml"


def _obstacle(route: dict, profile: str, profiles: dict) -> dict:
    if profile == "none":
        return {"x_m": 8.0, "y_m": 8.0, "z_m": 0.45}
    start, target = route["start"], route["target"]
    dx, dy = target["x_m"] - start["x_m"], target["y_m"] - start["y_m"]
    length = math.hypot(dx, dy)
    midpoint_x = (start["x_m"] + target["x_m"]) / 2
    midpoint_y = (start["y_m"] + target["y_m"]) / 2
    offset = float(profiles[profile]["normal_offset_m"])
    return {"x_m": midpoint_x - dy / length * offset,
            "y_m": midpoint_y + dx / length * offset, "z_m": 0.45}


def generate(config: dict) -> list[dict]:
    if config["status"] != "static_draft_not_preregistered_not_authorized":
        raise ValueError("B2当前只允许从静态草案生成不可执行候选计划")
    matrix = config["matrix"]
    blocks = int(matrix["complete_randomized_blocks_candidate"])
    split_counts = matrix["split_by_whole_block"]
    split_labels = (["train"] * int(split_counts["train_blocks"]) +
                    ["validation"] * int(split_counts["validation_blocks"]) +
                    ["sealed_test"] * int(split_counts["sealed_test_blocks"]))
    if len(split_labels) != blocks:
        raise ValueError("区组切分数量不等于完整区组数")
    # split顺序固定为train→validation→sealed_test，防止严格滞后历史把测试结果带回开发集。
    rng = random.Random(int(matrix["random_seed_candidate"]))
    scenarios = [(route, obstacle, localization)
                 for route in config["routes"]
                 for obstacle in config["obstacle_profiles"]
                 for localization in config["localization_levels"]]
    rows = []
    for block in range(1, blocks + 1):
        block_rows = list(scenarios)
        rng.shuffle(block_rows)
        for position, (route, obstacle, localization) in enumerate(block_rows, 1):
            index = len(rows) + 1
            rows.append({
                "plan_index": index, "task_id": f"b2-block{block:02d}-{position:02d}",
                "campaign": "w7_b2_risk_dataset", "dataset_version": config["dataset_version_candidate"],
                "model_split": split_labels[block - 1], "randomized_block": block,
                "block_position": position, "assignment_seed": int(matrix["random_seed_candidate"]),
                "environment_ready": False, "qualification_ready": False,
                "preacceptance_snapshot_required": True, "requires_fresh_environment": True,
                "route_id": route["id"], "start_x": float(route["start"]["x_m"]),
                "start_y": float(route["start"]["y_m"]),
                "start_yaw": float(route["start"]["yaw_rad"]),
                "target_x": float(route["target"]["x_m"]),
                "target_y": float(route["target"]["y_m"]),
                "target_yaw": float(route["target"]["yaw_rad"]), "timeout_sec": 120.0,
                "obstacle_profile": obstacle,
                "obstacle_position": _obstacle(route, obstacle, config["obstacle_profiles"]),
                "initial_perturbation": localization, "parameter_profile": "baseline",
                "environment_profile": f"natural__{route['id']}__{obstacle}__{localization}__baseline",
            })
    if len(rows) != int(matrix["candidate_total_tasks"]):
        raise ValueError("B2候选计划数量错误")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = generate(yaml.safe_load(args.config.read_text(encoding="utf-8")))
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode()).hexdigest()
    print(f"B2候选计划：{len(rows)}项；SHA-256={digest}；不可执行；未启动ROS/Gazebo")


if __name__ == "__main__":
    main()
