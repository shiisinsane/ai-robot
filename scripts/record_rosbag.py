#!/usr/bin/env python3
"""按M1录制配置档启动rosbag2，并在正常停止后检查完整性。"""

import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import signal
import subprocess
from typing import Any

import yaml

from check_rosbag import BagCheckError, _profile_topics, inspect_bag


def _load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict):
        raise BagCheckError("录制配置顶层必须是YAML映射")
    return config


def _git_commit() -> str:
    result = subprocess.run(
        ("git", "rev-parse", "--short=8", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _build_command(
    config: dict[str, Any],
    mode: str,
    output: Path,
    topics: list[str],
) -> list[str]:
    command = [
        "ros2",
        "bag",
        "record",
        "--output",
        str(output),
        "--storage",
        str(config["storage_id"]),
        "--serialization-format",
        str(config["serialization_format"]),
        "--max-bag-size",
        str(config["split"]["max_bag_size_bytes"]),
        "--max-bag-duration",
        str(config["split"]["max_bag_duration_sec"]),
        "--max-cache-size",
        str(config["max_cache_size_bytes"]),
        "--compression-mode",
        str(config["compression"]["mode"]),
        "--compression-format",
        str(config["compression"]["format"]),
    ]
    if config["rules"]["modes"][mode]["use_sim_time"]:
        command.append("--use-sim-time")
    command.extend(topics)
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument(
        "--profile",
        required=True,
        choices=("core", "navigation", "perception"),
    )
    parser.add_argument("--mode", required=True, choices=("sim", "real"))
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/common/rosbag_recording.yaml"),
    )
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()

    try:
        config = _load_config(args.config)
        pattern = config["rules"]["scenario_pattern"]
        if not re.fullmatch(pattern, args.scenario):
            raise BagCheckError("scenario只能使用2～48位小写字母、数字、_或-")

        required, optional = _profile_topics(config, args.profile)
        if (
            args.mode == "sim"
            and config["rules"]["modes"]["sim"]["clock_required"]
        ):
            required.add("/clock")
        topics = sorted(required | optional)

        output_root = args.output_root or Path(config["rules"]["output_root"])
        resolved_root = output_root.resolve()
        if resolved_root == Path("/"):
            raise BagCheckError("输出根目录不能是文件系统根目录")
        resolved_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        bag_name = (
            f"{timestamp}_{args.mode}_{args.scenario}_{_git_commit()}"
        )
        output = resolved_root / bag_name
        if output.exists():
            raise BagCheckError(f"输出目录已经存在：{output}")

        environment = os.environ.copy()
        log_dir = resolved_root / "_ros_logs"
        log_dir.mkdir(exist_ok=True)
        environment["ROS_LOG_DIR"] = str(log_dir)
        command = _build_command(config, args.mode, output, topics)

        print(f"开始录制：{output}")
        print("Topic：")
        for topic in topics:
            print(f"- {topic}")
        print("使用Ctrl-C正常停止；不得使用kill -9。")

        process = subprocess.Popen(
            command,
            env=environment,
            start_new_session=True,
        )
        try:
            return_code = process.wait()
        except KeyboardInterrupt:
            os.killpg(process.pid, signal.SIGINT)
            return_code = process.wait(timeout=30)
        if return_code != 0:
            raise BagCheckError(f"rosbag录制进程退出码：{return_code}")

        summary = inspect_bag(
            output,
            str(config["storage_id"]),
            required,
        )
        print("录制与完整性检查通过：")
        for item in summary:
            print(f"- {item}")
        print("下一步：复制证据清单模板并记录此目录的外部位置和校验值。")
        return 0
    except (
        BagCheckError,
        KeyError,
        OSError,
        subprocess.SubprocessError,
        yaml.YAMLError,
    ) as error:
        print(f"rosbag录制失败：{error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
