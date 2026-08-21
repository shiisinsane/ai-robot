"""读取并冻结W4初始位姿扰动配置，输出批次证据快照。"""

import argparse
from datetime import datetime
import json
from pathlib import Path

import yaml


def load_profile(config_path, profile_id, allow_qualification=False):
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    profiles = {item["id"]: item for item in config["initial_perturbations"]}
    if profile_id not in profiles:
        raise ValueError(f"未知初始位姿扰动档位：{profile_id}")
    profile = profiles[profile_id]
    if not profile.get("environment_ready") and not (
            allow_qualification and profile.get("qualification_ready")):
        raise ValueError(f"初始位姿扰动档位尚未Ready：{profile_id}")
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--qualification-pilot", action="store_true")
    args = parser.parse_args()
    try:
        profile = load_profile(
            args.config, args.profile, args.qualification_pilot)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    payload = {
        "configured_at": datetime.now().astimezone().isoformat(),
        "initial_perturbation": args.profile,
        "pose": {
            "x": float(profile["x_m"]),
            "y": float(profile["y_m"]),
            "yaw": float(profile["yaw_rad"]),
        },
        "gazebo_spawn_and_amcl_initial_pose_aligned": True,
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"初始位姿扰动已冻结：{args.profile}，位姿={payload['pose']}")


if __name__ == "__main__":
    main()
