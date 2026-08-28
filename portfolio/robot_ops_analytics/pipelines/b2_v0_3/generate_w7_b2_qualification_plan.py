#!/usr/bin/env python3
"""生成5条路线×3障碍的B2 GUI资格计划；不启动ROS/Gazebo。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from .generate_w7_b2_plan import _obstacle


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUALIFICATION = ROOT / "config/w7_b2_qualification_v0.1.yaml"


def generate(design: dict, qualification: dict) -> list[dict]:
    status = qualification["status"]
    execution_authorized = qualification["pilot_execution_authorized"]
    allowed = ((status in {"prepared_not_authorized", "pilot_paused_design_issue"}
                and not execution_authorized) or
               (status.endswith("_passed_waiting_next_instruction")
                and not execution_authorized) or
               (qualification["status"] == "pilot_authorized" and qualification[
                "pilot_execution_authorized"]) or
               (qualification["status"] == "pilot_rerun_authorized" and qualification[
                "pilot_execution_authorized"]) or
               (qualification["status"] == "pilot_task_authorized" and qualification[
                "pilot_execution_authorized"]))
    if not allowed:
        raise ValueError("B2资格配置状态与授权开关不一致")
    rows = []
    start_domain = int(qualification["start_domain_candidate"])
    for route in design["routes"]:
        for profile in design["obstacle_profiles"]:
            sequence = len(rows) + 1
            rows.append({
                "qualification_sequence": sequence,
                "plan_index": sequence,
                "repetition": 1,
                "task_id": f"b2-pilot-{route['id']}-{profile}",
                "campaign": "w7_b2_qualification", "dataset_version": qualification["dataset_version"],
                "formal_dataset_admission": False, "environment_ready": False,
                "qualification_ready": True, "preacceptance_snapshot_required": True,
                "route_id": route["id"], "start_x": route["start"]["x_m"],
                "start_y": route["start"]["y_m"], "start_yaw": route["start"]["yaw_rad"],
                "target_x": route["target"]["x_m"], "target_y": route["target"]["y_m"],
                "target_yaw": route["target"]["yaw_rad"], "timeout_sec": 120.0,
                "obstacle_profile": profile,
                "obstacle_position": _obstacle(route, profile, design["obstacle_profiles"]),
                "initial_perturbation": "none", "parameter_profile": "baseline",
                "environment_profile": f"qualification__{route['id']}__{profile}__none__baseline",
                "ros_domain_id": start_domain + sequence - 1,
                "gazebo_partition": f"{qualification['gazebo_partition_prefix']}_{sequence:02d}",
                "requires_gui": True, "requires_fresh_environment": True,
            })
    if len(rows) != int(qualification["pilot_count"]):
        raise ValueError("B2资格计划数量错误")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", type=Path, default=DEFAULT_QUALIFICATION)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    qualification = yaml.safe_load(args.qualification.read_text(encoding="utf-8"))
    design_path = Path(qualification["source_design"])
    design = yaml.safe_load(design_path.read_text(encoding="utf-8"))
    rows = generate(design, qualification)
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    state = "已授权资格Pilot" if qualification["pilot_execution_authorized"] else "未授权执行"
    print(f"B2资格计划：15项；SHA-256={hashlib.sha256(payload.encode()).hexdigest()}；{state}")


if __name__ == "__main__":
    main()
