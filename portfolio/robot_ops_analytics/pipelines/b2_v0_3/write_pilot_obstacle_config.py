#!/usr/bin/env python3
"""从B2资格计划为单个Pilot生成可供既有环境控制器读取的障碍配置。"""

import argparse
import json
from pathlib import Path


def build(row: dict) -> dict:
    position = row["obstacle_position"]
    profile = {"id": row["obstacle_profile"], "environment_ready": False,
               "qualification_ready": True, "world": "m5_slam",
               "model": "temporary_obstacle", "x_m": position["x_m"],
               "y_m": position["y_m"], "z_m": position.get("z_m", 0.45),
               "route_id": row["route_id"]}
    return {"version": "roa-w7-b2-pilot-obstacle-runtime-v0.1",
            "source_task_id": row["task_id"], "obstacle_profiles": [profile]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.plan.read_text(encoding="utf-8").splitlines()]
    selected = [row for row in rows if row["task_id"] == args.task_id]
    if len(selected) != 1:
        raise SystemExit("资格计划中的task_id不唯一或不存在")
    import yaml
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(build(selected[0]), allow_unicode=True, sort_keys=False),
                           encoding="utf-8")
    print(f"单项障碍配置已生成：{args.task_id}")


if __name__ == "__main__":
    main()
