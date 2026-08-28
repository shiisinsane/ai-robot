#!/usr/bin/env python3
"""在启动ROS/Gazebo前校验B2计划、命令参数和障碍配置的一致性。"""

import argparse
import json
from pathlib import Path

import yaml


def _equal(left, right):
    return abs(float(left) - float(right)) <= 1e-9


def validate(plan_path, task_id, environment_profile, obstacle_profile,
             initial_perturbation, initial_pose, obstacle_config_path):
    rows = [json.loads(line) for line in Path(plan_path).read_text(encoding="utf-8").splitlines()
            if line.strip()]
    matches = [row for row in rows if row.get("task_id") == task_id]
    if len(matches) != 1:
        raise ValueError("B2冻结计划中的task-id不存在或不唯一")
    task = matches[0]
    required = {"qualification_sequence", "repetition", "campaign", "dataset_version",
                "route_id", "start_x", "start_y", "start_yaw", "target_x", "target_y",
                "target_yaw", "obstacle_position", "ros_domain_id", "gazebo_partition"}
    missing = sorted(required - task.keys())
    if missing or task.get("campaign") != "w7_b2_qualification":
        raise ValueError(f"B2计划行不符合Schema，缺失={missing}")
    comparisons = {
        "environment-profile": (environment_profile, task["environment_profile"]),
        "obstacle-profile": (obstacle_profile, task["obstacle_profile"]),
        "initial-perturbation": (initial_perturbation, task["initial_perturbation"]),
    }
    mismatches = [name for name, values in comparisons.items() if values[0] != values[1]]
    expected_pose = (task["start_x"], task["start_y"], task["start_yaw"])
    if not all(_equal(actual, expected) for actual, expected in zip(initial_pose, expected_pose)):
        mismatches.append("initial-pose")
    obstacle = yaml.safe_load(Path(obstacle_config_path).read_text(encoding="utf-8"))
    profiles = obstacle.get("obstacle_profiles", [])
    if obstacle.get("source_task_id") != task_id or len(profiles) != 1:
        mismatches.append("obstacle-source-task")
    else:
        profile = profiles[0]
        if profile.get("id") != task["obstacle_profile"] or profile.get("route_id") != task["route_id"]:
            mismatches.append("obstacle-profile-route")
        expected = task["obstacle_position"]
        if not all(_equal(profile.get(key), expected[key]) for key in ("x_m", "y_m", "z_m")):
            mismatches.append("obstacle-position")
    if mismatches:
        raise ValueError("B2启动参数与冻结计划不一致：" + ",".join(mismatches))
    return task


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--environment-profile", required=True)
    parser.add_argument("--obstacle-profile", required=True)
    parser.add_argument("--obstacle-config", type=Path, required=True)
    parser.add_argument("--initial-perturbation", required=True)
    parser.add_argument("--initial-pose", nargs=3, type=float, required=True)
    args = parser.parse_args()
    try:
        validate(args.plan, args.task_id, args.environment_profile, args.obstacle_profile,
                 args.initial_perturbation, args.initial_pose, args.obstacle_config)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise SystemExit(str(error)) from error
    print("B2启动参数与冻结计划一致性门禁：通过")


if __name__ == "__main__":
    main()
