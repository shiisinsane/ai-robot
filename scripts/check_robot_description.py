#!/usr/bin/env python3
"""展开并验证M2 URDF/Xacro机器人描述。"""

import argparse
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

if __package__:
    from scripts.check_robot_model import load_model
else:
    from check_robot_model import load_model


class DescriptionError(ValueError):
    """机器人描述不满足W2/W3基线。"""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DescriptionError(message)


def expand_description(xacro_path: Path, model_path: Path) -> ET.Element:
    """展开Xacro并返回URDF根元素。"""
    result = subprocess.run(
        [
            "xacro",
            str(xacro_path),
            f"model_config:={model_path.resolve()}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return ET.fromstring(result.stdout)


def _xyz(element: ET.Element) -> list[float]:
    origin = element.find("origin")
    _require(origin is not None, "Joint缺少origin")
    return [float(value) for value in origin.attrib["xyz"].split()]


def validate_description(
    root: ET.Element,
    model: dict,
) -> list[str]:
    """检查Link、Joint、惯量和W2参数映射。"""
    _require(root.tag == "robot", "展开结果根元素必须是robot")
    _require(root.attrib.get("name") == "ai_robot", "机器人名称必须为ai_robot")
    _require(root.find("gazebo") is None, "W3不得提前加入Gazebo插件")
    _require(root.find("ros2_control") is None, "W3不得提前加入ros2_control")

    links = {
        element.attrib["name"]: element
        for element in root.findall("link")
    }
    joints = {
        element.attrib["name"]: element for element in root.findall("joint")
    }
    expected_links = {
        "base_link",
        "base_footprint",
        "left_wheel_link",
        "right_wheel_link",
        "front_caster_link",
        "rear_caster_link",
    }
    expected_joints = {
        "base_footprint_joint",
        "left_wheel_joint",
        "right_wheel_joint",
        "front_caster_joint",
        "rear_caster_joint",
    }
    _require(set(links) == expected_links, "Link集合与W2基线不一致")
    _require(set(joints) == expected_joints, "Joint集合与W2基线不一致")

    for name, link in links.items():
        if name == "base_footprint":
            _require(link.find("inertial") is None, "辅助Frame不得包含惯量")
            continue
        _require(link.find("visual") is not None, f"{name}缺少visual")
        _require(link.find("collision") is not None, f"{name}缺少collision")
        inertial = link.find("inertial")
        _require(inertial is not None, f"{name}缺少inertial")
        mass = inertial.find("mass")
        _require(
            mass is not None and float(mass.attrib["value"]) > 0,
            f"{name}质量必须为正数",
        )

    drive = model["drive"]
    for side in ("left", "right"):
        wheel = drive["wheels"][side]
        joint = joints[wheel["joint_name"]]
        _require(joint.attrib.get("type") == "continuous", f"{side}轮必须是连续关节")
        axis = joint.find("axis")
        _require(axis is not None, f"{side}轮缺少轴向")
        _require(
            [float(value) for value in axis.attrib["xyz"].split()]
            == [float(value) for value in drive["joint_axis"]],
            f"{side}轮轴向与W2参数不一致",
        )
        _require(
            _xyz(joint) == [float(value) for value in wheel["xyz"]],
            f"{side}轮位置错误",
        )

    footprint_joint = joints["base_footprint_joint"]
    _require(
        footprint_joint.attrib.get("type") == "fixed",
        "base_footprint必须固定",
    )
    _require(
        footprint_joint.find("parent").attrib["link"] == "base_link",
        "base_footprint不得改变odom主链",
    )

    return [
        "6个Link和5个Joint完整且名称唯一",
        "物理Link均包含visual、collision和正质量inertial",
        "左右轮位置、轴向和连续关节映射W2参数",
        "未提前加入Gazebo或ros2_control配置",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xacro",
        type=Path,
        default=Path(
            "src/robot_core/ai_robot_description/urdf/ai_robot.urdf.xacro"
        ),
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("config/common/robot_model.yaml"),
    )
    args = parser.parse_args()
    try:
        root = expand_description(args.xacro, args.model)
        summary = validate_description(root, load_model(args.model))
    except (
        DescriptionError,
        ET.ParseError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"机器人描述检查失败：{error}")
        return 1
    print(f"机器人描述检查通过：{args.xacro}")
    for item in summary:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
