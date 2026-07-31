#!/usr/bin/env python3
"""检查rosbag2元数据、Topic完整性和最小可回放条件。"""

import argparse
from pathlib import Path
from typing import Any

import rosbag2_py
import yaml


class BagCheckError(ValueError):
    """rosbag不满足检查规则。"""


def _load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict):
        raise BagCheckError("录制配置顶层必须是YAML映射")
    return config


def _profile_topics(
    config: dict[str, Any], profile_name: str
) -> tuple[set[str], set[str]]:
    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        raise BagCheckError(f"未知录制配置档：{profile_name}")

    required: set[str] = set()
    optional: set[str] = set()
    visited: set[str] = set()
    current_name: str | None = profile_name
    while current_name:
        if current_name in visited:
            raise BagCheckError("录制配置档存在循环继承")
        visited.add(current_name)
        current = profiles.get(current_name)
        if not isinstance(current, dict):
            raise BagCheckError(f"录制配置档{current_name}无效")
        required.update(current.get("required_topics", []))
        optional.update(current.get("optional_topics", []))
        current_name = current.get("extends")
    optional -= required
    return required, optional


def inspect_bag(
    bag_path: Path,
    storage_id: str,
    required_topics: set[str],
) -> list[str]:
    if not bag_path.is_dir():
        raise BagCheckError(f"rosbag目录不存在：{bag_path}")
    if not (bag_path / "metadata.yaml").is_file():
        raise BagCheckError("缺少metadata.yaml，录制可能未正常停止")

    metadata = rosbag2_py.Info().read_metadata(str(bag_path), storage_id)
    if metadata.message_count <= 0:
        raise BagCheckError("rosbag没有消息")
    if metadata.duration.nanoseconds <= 0:
        raise BagCheckError("rosbag持续时间必须大于0")

    topic_counts = {
        item.topic_metadata.name: item.message_count
        for item in metadata.topics_with_message_count
    }
    missing = sorted(required_topics - topic_counts.keys())
    if missing:
        raise BagCheckError(f"缺少必需Topic：{', '.join(missing)}")

    empty = sorted(
        topic for topic in required_topics if topic_counts.get(topic, 0) <= 0
    )
    if empty:
        raise BagCheckError(f"必需Topic没有消息：{', '.join(empty)}")

    return [
        f"总消息数：{metadata.message_count}",
        f"持续时间：{metadata.duration.nanoseconds / 1e9:.3f} s",
        f"Topic数：{len(topic_counts)}",
        "必需Topic均存在且至少包含1条消息",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag_path", type=Path)
    parser.add_argument(
        "--profile",
        choices=("core", "navigation", "perception"),
    )
    parser.add_argument("--required-topic", action="append", default=[])
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/common/rosbag_recording.yaml"),
    )
    parser.add_argument("--storage-id")
    args = parser.parse_args()

    try:
        config = _load_config(args.config)
        required = set(args.required_topic)
        if args.profile:
            profile_required, _ = _profile_topics(config, args.profile)
            required.update(profile_required)
        storage_id = args.storage_id or config.get("storage_id", "sqlite3")
        summary = inspect_bag(args.bag_path, storage_id, required)
    except (OSError, yaml.YAMLError, RuntimeError, BagCheckError) as error:
        print(f"rosbag检查失败：{error}")
        return 1

    print(f"rosbag检查通过：{args.bag_path}")
    for item in summary:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
