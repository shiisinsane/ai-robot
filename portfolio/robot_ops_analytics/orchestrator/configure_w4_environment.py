"""按W4矩阵确定性配置Gazebo环境，并保存可追溯证据。"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess

import yaml


PARKED_POSE = (8.0, 8.0, 0.45)


def load_profile(config_path, profile_id):
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    profiles = {item["id"]: item for item in config["obstacle_profiles"]}
    if profile_id not in profiles:
        raise ValueError(f"未知障碍物档位：{profile_id}")
    profile = profiles[profile_id]
    if not profile.get("environment_ready"):
        raise ValueError(f"障碍物档位尚未Ready：{profile_id}")
    return profile


def desired_pose(profile):
    if profile["id"] == "none":
        return PARKED_POSE
    return (float(profile["x_m"]), float(profile["y_m"]),
            float(profile.get("z_m", 0.45)))


def set_pose(profile, runner=subprocess.run):
    x, y, z = desired_pose(profile)
    world = profile.get("world", "m5_slam")
    model = profile.get("model", "temporary_obstacle")
    command = [
        "ign", "service", "-s", f"/world/{world}/set_pose",
        "--reqtype", "ignition.msgs.Pose",
        "--reptype", "ignition.msgs.Boolean", "--timeout", "5000",
        "--req", (f'name: "{model}", position: '
                  f'{{x: {x:.6f}, y: {y:.6f}, z: {z:.6f}}}'),
    ]
    result = runner(command, check=False, capture_output=True, text=True,
                    timeout=8.0)
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0 or "data: true" not in output.lower():
        raise RuntimeError(
            f"设置障碍物位姿失败（返回码{result.returncode}）：{output}")
    return command, output, (x, y, z)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        profile = load_profile(args.config, args.profile)
        command, output, pose = set_pose(profile)
    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error)) from error
    payload = {
        "configured_at": datetime.now().astimezone().isoformat(),
        "obstacle_profile": args.profile,
        "model": profile.get("model", "temporary_obstacle"),
        "world": profile.get("world", "m5_slam"),
        "pose": {"x": pose[0], "y": pose[1], "z": pose[2]},
        "service_success": True,
        "command": command,
        "service_output": output,
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"障碍物环境已配置：{args.profile}，位置={pose}")


if __name__ == "__main__":
    main()
