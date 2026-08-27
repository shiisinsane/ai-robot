"""从W4 YAML定义生成确定性的JSONL任务计划；不启动ROS。"""

import argparse
from itertools import product
import json
from pathlib import Path

import yaml


def _case(index, campaign, route, obstacle, perturbation, parameter, repetition,
          fault=None):
    fault_id = fault["id"] if fault else None
    profile = "__".join(filter(None, (
        campaign, obstacle["id"], perturbation["id"], parameter["id"], fault_id)))
    ready = all(item.get("environment_ready", False) for item in
                (obstacle, perturbation, parameter)) and (
                    fault is None or fault.get("environment_ready", False))
    return {
        "plan_index": index,
        "task_id": f"w4-{index:04d}",
        "campaign": campaign,
        "run_origin": "natural" if fault is None else "fault_injection",
        "fault_injection_type": fault_id,
        "environment_profile": profile,
        "environment_ready": ready,
        "qualification_ready": fault is None and sum(
            bool(item.get("qualification_ready", False)) and
            not bool(item.get("environment_ready", False))
            for item in (obstacle, perturbation, parameter)) == 1 and all(
                item.get("environment_ready", False) or
                item.get("qualification_ready", False)
                for item in (obstacle, perturbation, parameter)),
        "route_id": route["route_id"],
        "start_x": route["start_x"], "start_y": route["start_y"],
        "start_yaw": route["start_yaw"],
        "target_x": route["target_x"], "target_y": route["target_y"],
        "target_yaw": route["target_yaw"], "timeout_sec": route["timeout_sec"],
        "obstacle_profile": obstacle["id"],
        "initial_perturbation": perturbation["id"],
        "parameter_profile": parameter["id"],
        "repetition": repetition,
        "requires_reset_before_task": True,
    }


def generate(config):
    cases = []
    natural = config["natural_campaign"]
    for route, obstacle, perturbation, parameter, repetition in product(
            config["routes"], config["obstacle_profiles"],
            config["initial_perturbations"], config["parameter_profiles"],
            range(1, natural["repetitions"] + 1)):
        cases.append(_case(len(cases) + 1, "natural", route, obstacle,
                           perturbation, parameter, repetition))
    fault_campaign = config["fault_campaign"]
    obstacle = next(x for x in config["obstacle_profiles"]
                    if x["id"] == fault_campaign["fixed_obstacle_profile"])
    perturbation = next(x for x in config["initial_perturbations"]
                        if x["id"] == fault_campaign["fixed_initial_perturbation"])
    for fault, route, parameter, repetition in product(
            fault_campaign["fault_profiles"], config["routes"],
            config["parameter_profiles"],
            range(1, fault_campaign["repetitions"] + 1)):
        cases.append(_case(len(cases) + 1, "fault", route, obstacle,
                           perturbation, parameter, repetition, fault))
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(
        "portfolio/robot_ops_analytics/config/w4_matrix_v1.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    cases = generate(config)
    expected = config["expected_counts"]
    if len(cases) != expected["total"]:
        raise SystemExit(f"矩阵数量错误：生成{len(cases)}，期望{expected['total']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n"
                                   for x in cases), encoding="utf-8")
    ready = sum(x["environment_ready"] for x in cases)
    print(f"W4计划已生成：{len(cases)}项，可立即执行{ready}项，待准备{len(cases)-ready}项")


if __name__ == "__main__":
    main()
