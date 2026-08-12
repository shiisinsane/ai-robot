#!/usr/bin/env python3
"""验证M1机器可读接口契约的结构与关键安全约束。"""

import argparse
from pathlib import Path
from typing import Any

import yaml


class ContractError(ValueError):
    """接口契约不满足基线规则。"""


def load_contract(path: Path) -> dict[str, Any]:
    """读取YAML契约并确认顶层为映射。"""
    with path.open(encoding="utf-8") as stream:
        contract = yaml.safe_load(stream)
    if not isinstance(contract, dict):
        raise ContractError("契约顶层必须是YAML映射")
    return contract


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def validate_contract(contract: dict[str, Any]) -> list[str]:
    """返回验证摘要；失败时抛出ContractError。"""
    _require(contract.get("interface_version") == "m1.v2", "接口版本必须为m1.v2")
    _require(contract.get("robot_namespace") == "robot", "默认机器人命名空间必须为robot")

    profiles = contract.get("qos_profiles")
    _require(isinstance(profiles, dict) and profiles, "必须定义QoS配置档")
    for name, profile in profiles.items():
        _require(isinstance(profile, dict), f"QoS配置档{name}必须是映射")
        _require(profile.get("history") == "keep_last", f"{name}必须使用keep_last")
        depth = profile.get("depth")
        _require(isinstance(depth, int) and depth > 0, f"{name}的depth必须是正整数")
        _require(
            profile.get("reliability") in {"reliable", "best_effort"},
            f"{name}的reliability无效",
        )
        _require(
            profile.get("durability") in {"volatile", "transient_local"},
            f"{name}的durability无效",
        )

    groups = {
        "topics": contract.get("topics"),
        "services": contract.get("services"),
        "actions": contract.get("actions"),
    }
    for group_name, entries in groups.items():
        _require(isinstance(entries, list) and entries, f"{group_name}必须是非空列表")

    all_entries = [
        entry for entries in groups.values() for entry in entries
    ]
    identities: set[tuple[str, str]] = set()
    names: set[str] = set()
    for entry in all_entries:
        _require(isinstance(entry, dict), "接口条目必须是映射")
        name = entry.get("name")
        interface_type = entry.get("type")
        _require(isinstance(name, str) and name, "接口名称不能为空")
        _require(not name.startswith("/"), f"接口{name}必须使用相对名称")
        _require(
            isinstance(interface_type, str) and interface_type,
            f"{name}缺少类型",
        )
        identity = (name, interface_type)
        _require(
            identity not in identities,
            f"接口名称和类型重复：{name}",
        )
        _require(name not in names, f"公共接口名称重复：{name}")
        identities.add(identity)
        names.add(name)

    for topic in groups["topics"]:
        name = topic["name"]
        qos_profile = topic.get("qos_profile")
        _require(qos_profile in profiles, f"Topic {name}引用未知QoS配置档")
        for field in ("min_rate_hz", "timeout_sec"):
            if field in topic:
                value = topic[field]
                _require(
                    isinstance(value, (int, float)) and value > 0,
                    f"Topic {name}的{field}必须为正数",
                )

    time_rules = contract.get("time", {})
    _require(
        time_rules.get("sim", {}).get("use_sim_time") is True,
        "仿真必须使用仿真时间",
    )
    _require(
        time_rules.get("sim", {}).get("clock_topic") == "/clock",
        "仿真时钟必须为/clock",
    )
    _require(
        time_rules.get("real", {}).get("use_sim_time") is False,
        "实体不得使用仿真时间",
    )
    _require(
        time_rules.get("watchdog_clock") == "steady",
        "安全看门狗必须使用稳态时钟",
    )

    frame_rules = contract.get("frames", {})
    transforms = frame_rules.get("transforms")
    _require(isinstance(transforms, list), "必须定义TF变换责任")
    pairs: set[tuple[str, str]] = set()
    for transform in transforms:
        parent = transform.get("parent")
        child = transform.get("child")
        if child is None:
            child = transform.get("child_pattern")
        _require(parent and child, "TF规则必须定义父子Frame")
        pair = (parent, child)
        _require(pair not in pairs, f"TF责任重复：{parent} -> {child}")
        _require(
            transform.get("exclusive") is True,
            f"TF {parent} -> {child}必须是唯一发布者",
        )
        pairs.add(pair)

    _require(("map", "odom") in pairs, "缺少map -> odom")
    _require(("odom", "base_link") in pairs, "缺少odom -> base_link")

    topic_count = len(groups["topics"])
    service_count = len(groups["services"])
    action_count = len(groups["actions"])
    _require(
        (topic_count, service_count, action_count) == (15, 2, 3),
        "公共接口数量异常",
    )
    task_actions = [entry for entry in groups["actions"]
                    if entry["name"] == "task/execute"]
    _require(len(task_actions) == 1, "必须定义唯一task/execute Action")
    _require(task_actions[0]["type"] ==
             "robot_interfaces/action/ExecuteRobotTask",
             "任务Action类型错误")

    return [
        f"{topic_count}个Topic均引用有效QoS配置档",
        f"{service_count}个Service和{action_count}个Action名称、类型唯一",
        "仿真与实体时间规则有效",
        "map -> odom -> base_link TF责任链完整",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "contract",
        nargs="?",
        type=Path,
        default=Path("config/common/interface_contract.yaml"),
    )
    args = parser.parse_args()

    try:
        summary = validate_contract(load_contract(args.contract))
    except (OSError, yaml.YAMLError, ContractError) as error:
        print(f"接口契约检查失败：{error}")
        return 1

    print(f"接口契约检查通过：{args.contract}")
    for item in summary:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
