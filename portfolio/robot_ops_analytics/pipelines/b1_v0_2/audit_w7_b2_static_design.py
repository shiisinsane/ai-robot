#!/usr/bin/env python3
"""离线审计W7 B2候选路线、障碍位置和矩阵数量。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config/w7_b2_design_draft_v0.1.yaml"


def audit(config: dict) -> dict:
    geometry = config["geometry"]
    room = geometry["room_inner_bounds_m"]
    inflation = float(geometry["global_inflation_radius_m"])
    half_obstacle = float(geometry["obstacle_size_m"]["x"]) / 2 + inflation
    usable = {"min_x": room["min_x"] + inflation, "max_x": room["max_x"] - inflation,
              "min_y": room["min_y"] + inflation, "max_y": room["max_y"] - inflation}
    route_results = []
    for route in config["routes"]:
        start, target = route["start"], route["target"]
        dx, dy = target["x_m"] - start["x_m"], target["y_m"] - start["y_m"]
        length = math.hypot(dx, dy)
        midpoint = {"x_m": (start["x_m"] + target["x_m"]) / 2,
                    "y_m": (start["y_m"] + target["y_m"]) / 2}
        normal = {"x_m": -dy / length, "y_m": dx / length}
        obstacles = {}
        for profile in ("low", "medium"):
            offset = config["obstacle_profiles"][profile]["normal_offset_m"]
            point = {"x_m": midpoint["x_m"] + normal["x_m"] * offset,
                     "y_m": midpoint["y_m"] + normal["y_m"] * offset}
            corridors = [point["x_m"] - half_obstacle - usable["min_x"],
                         usable["max_x"] - point["x_m"] - half_obstacle,
                         point["y_m"] - half_obstacle - usable["min_y"],
                         usable["max_y"] - point["y_m"] - half_obstacle]
            obstacles[profile] = {"position": point, "largest_axis_corridor_m": max(corridors)}
        endpoints_inside = all(usable["min_x"] <= p["x_m"] <= usable["max_x"] and
                               usable["min_y"] <= p["y_m"] <= usable["max_y"]
                               for p in (start, target))
        endpoint_clearance = length / 2 - half_obstacle
        passed = (endpoints_inside and length >= geometry["minimum_route_length_m"] and
                  endpoint_clearance >= geometry["minimum_endpoint_clearance_m"] and
                  obstacles["medium"]["largest_axis_corridor_m"] >=
                  geometry["minimum_one_side_detour_corridor_m"])
        route_results.append({"route_id": route["id"], "length_m": length,
                              "endpoints_inside_usable_bounds": endpoints_inside,
                              "endpoint_clearance_from_medium_inflation_m": endpoint_clearance,
                              "obstacles": obstacles, "passed": passed})
    expected_cells = (len(config["routes"]) * len(config["obstacle_profiles"]) *
                      len(config["localization_levels"]))
    blocks = config["matrix"]["complete_randomized_blocks_candidate"]
    matrix_passed = (expected_cells == config["matrix"]["scenario_cells"] and
                     expected_cells * blocks == config["matrix"]["candidate_total_tasks"] and
                     sum(config["matrix"]["split_by_whole_block"].values()) == blocks)
    return {"version": config["version"], "static_geometry_passed": all(
                row["passed"] for row in route_results),
            "matrix_passed": matrix_passed, "scenario_cells": expected_cells,
            "candidate_total_tasks": expected_cells * blocks,
            "limitations": "静态几何通过不等于costmap、Nav2或GUI资格通过",
            "routes": route_results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(yaml.safe_load(args.config.read_text(encoding="utf-8")))
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    if not result["static_geometry_passed"] or not result["matrix_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
