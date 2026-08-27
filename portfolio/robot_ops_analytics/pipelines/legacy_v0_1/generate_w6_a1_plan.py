"""从冻结的W6 A1预注册配置生成30槽位确定性JSONL计划；不启动ROS。"""

import argparse
import json
from pathlib import Path

import yaml


DEFAULT_CONFIG = Path(__file__).parents[2] / "config/w6_a1_validation_v0.1.yaml"


def generate(config):
    if config["status"] != "frozen_before_execution":
        raise ValueError("A1配置未处于执行前冻结状态")
    fixed = config["fixed_conditions"]
    groups = {
        value["obstacle_profile"]: value for value in config["groups"].values()
    }
    cases = []
    for slot in config["assignment"]["sequence"]:
        obstacle = slot["obstacle_profile"]
        if obstacle not in groups:
            raise ValueError(f"槽位引用未知障碍组：{obstacle}")
        run_order = int(slot["run_order"])
        cases.append({
            "plan_index": run_order,
            "task_id": f"a1-{run_order:04d}",
            "campaign": "w6_a1_controlled_validation",
            "experiment_purpose": config["experiment_purpose"],
            "dataset_version": config["validation_dataset_version"],
            "run_origin": fixed["run_origin"],
            "fault_injection_type": None,
            "environment_profile": (
                f"natural__{obstacle}__{fixed['localization_perturbation_level']}"
                f"__{fixed['parameter_version']}"),
            "environment_ready": True,
            "qualification_ready": False,
            "route_id": fixed["route_id"],
            "start_x": float(fixed["start_pose"]["x_m"]),
            "start_y": float(fixed["start_pose"]["y_m"]),
            "start_yaw": float(fixed["start_pose"]["yaw_rad"]),
            "target_x": float(fixed["target_pose"]["x_m"]),
            "target_y": float(fixed["target_pose"]["y_m"]),
            "target_yaw": float(fixed["target_pose"]["yaw_rad"]),
            "timeout_sec": float(fixed["task_timeout_sec"]),
            "obstacle_profile": obstacle,
            "initial_perturbation": fixed["localization_perturbation_level"],
            "parameter_profile": fixed["parameter_version"],
            "repetition": int(slot["block"]),
            "validation_block": int(slot["block"]),
            "block_position": int(slot["position"]),
            "assignment_seed": int(config["assignment"]["seed"]),
            "requires_reset_before_task": True,
        })
    expected = sum(int(group["required_valid_tasks"]) for group in groups.values())
    if len(cases) != expected:
        raise ValueError(f"A1槽位数量错误：{len(cases)}，期望{expected}")
    if len({case["task_id"] for case in cases}) != len(cases):
        raise ValueError("A1任务ID不唯一")
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    try:
        cases = generate(config)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(
        json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n" for case in cases
    ), encoding="utf-8")
    print(f"A1计划已生成：{len(cases)}项，low=15，medium=15；未启动ROS/Gazebo")


if __name__ == "__main__":
    main()
