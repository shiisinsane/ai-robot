"""离线审计B1长路线、障碍膨胀范围和几何绕行空间。"""

import argparse
import json
from pathlib import Path

import yaml


DEFAULT_CONFIG = Path(__file__).parents[2] / "config/w6_b1_long_route_draft_v0.2.yaml"


def _inside(box, point):
    return box["min_x"] <= point["x_m"] <= box["max_x"] and box["min_y"] <= point["y_m"] <= box["max_y"]


def audit(config):
    route = config["route"]
    fixed = config["fixed_conditions"]
    room = config["static_geometry"]["room_inner_bounds_m"]
    radius = float(fixed["global_inflation_radius_m"])
    half_x = float(fixed["obstacle_size_m"]["x"]) / 2.0 + radius
    half_y = float(fixed["obstacle_size_m"]["y"]) / 2.0 + radius
    usable = {
        "min_x": float(room["min_x"]) + radius,
        "max_x": float(room["max_x"]) - radius,
        "min_y": float(room["min_y"]) + radius,
        "max_y": float(room["max_y"]) - radius,
    }
    start = route["start_pose"]
    target = route["target_pose"]
    results = []
    for profile in config["obstacle_profiles"]:
        position = profile["position"]
        if profile["id"] == "none":
            results.append({"profile": "none", "status": "pass", "reason": "障碍停在场外"})
            continue
        box = {
            "min_x": float(position["x_m"]) - half_x,
            "max_x": float(position["x_m"]) + half_x,
            "min_y": float(position["y_m"]) - half_y,
            "max_y": float(position["y_m"]) + half_y,
        }
        north = usable["max_y"] - box["max_y"]
        south = box["min_y"] - usable["min_y"]
        endpoint_free = not _inside(box, start) and not _inside(box, target)
        detour = max(north, south)
        status = "pass" if endpoint_free and detour >= config["static_geometry"]["minimum_detour_corridor_m"] else "fail"
        results.append({
            "profile": profile["id"],
            "status": status,
            "inflated_box_m": box,
            "start_and_target_outside_inflation": endpoint_free,
            "north_detour_corridor_m": round(north, 3),
            "south_detour_corridor_m": round(south, 3),
            "largest_detour_corridor_m": round(detour, 3),
        })
    return {
        "config_version": config["version"],
        "status": "pass" if all(item["status"] == "pass" for item in results) else "fail",
        "method": "conservative axis-aligned geometry using global inflation radius",
        "limitations": "静态几何通过不等于Nav2规划、控制或安全资格通过",
        "usable_room_center_bounds_m": usable,
        "profiles": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    result = audit(config)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
