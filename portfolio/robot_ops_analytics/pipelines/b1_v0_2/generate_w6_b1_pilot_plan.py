"""生成B1三个资格Pilot的确定性计划；不启动ROS或Gazebo。"""

import argparse
import json
from pathlib import Path

import yaml


DEFAULT_CONFIG = Path(__file__).parents[2] / "config/w6_b1_long_route_draft_v0.2.yaml"


def generate(config):
    if config["execution_authorized"] not in {
            "qualification_pilot_only",
            "pilot_completed_formal_experiment_not_authorized"}:
        raise ValueError("B1资格计划状态无效")
    route = config["route"]
    rows = []
    for index, obstacle in enumerate(config["obstacle_profiles"], 1):
        rows.append({
            "plan_index": index,
            "task_id": f"b1-pilot-{obstacle['id']}",
            "campaign": "w6_b1_qualification",
            "dataset_version": config["planned_dataset_version"],
            "environment_profile": f"natural__{obstacle['id']}__none__baseline",
            "environment_ready": False,
            "qualification_ready": True,
            "route_id": route["route_id"],
            "start_x": float(route["start_pose"]["x_m"]),
            "start_y": float(route["start_pose"]["y_m"]),
            "start_yaw": float(route["start_pose"]["yaw_rad"]),
            "target_x": float(route["target_pose"]["x_m"]),
            "target_y": float(route["target_pose"]["y_m"]),
            "target_yaw": float(route["target_pose"]["yaw_rad"]),
            "timeout_sec": float(route["task_timeout_sec"]),
            "obstacle_profile": obstacle["id"],
            "initial_perturbation": "none",
            "parameter_profile": "baseline",
            "repetition": 1,
        })
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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    print("B1资格计划已生成：none/low/medium各1项；未启动ROS/Gazebo")


if __name__ == "__main__":
    main()
