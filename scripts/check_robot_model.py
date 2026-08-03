#!/usr/bin/env python3
"""验证M2机器人本体参数的结构、物理值和M1契约边界。"""

import argparse
import math
from pathlib import Path
from typing import Any

import yaml


class ModelContractError(ValueError):
    """机器人模型参数不满足M2基线。"""


def load_model(path: Path) -> dict[str, Any]:
    """读取模型YAML并确认顶层为映射。"""
    with path.open(encoding="utf-8") as stream:
        model = yaml.safe_load(stream)
    if not isinstance(model, dict):
        raise ModelContractError("模型参数顶层必须是YAML映射")
    return model


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ModelContractError(message)


def _positive(value: Any, name: str) -> float:
    _require(
        isinstance(value, (int, float))
        and math.isfinite(value)
        and value > 0,
        f"{name}必须是有限正数",
    )
    return float(value)


def _vector(value: Any, name: str, size: int = 3) -> list[float]:
    _require(
        isinstance(value, list) and len(value) == size,
        f"{name}必须有{size}项",
    )
    _require(
        all(
            isinstance(item, (int, float)) and math.isfinite(item)
            for item in value
        ),
        f"{name}必须全部是有限数值",
    )
    return [float(item) for item in value]


def _validate_inertia(inertia: dict[str, Any], name: str) -> None:
    _require(isinstance(inertia, dict), f"{name}必须是映射")
    ixx = _positive(inertia.get("ixx"), f"{name}.ixx")
    iyy = _positive(inertia.get("iyy"), f"{name}.iyy")
    izz = _positive(inertia.get("izz"), f"{name}.izz")
    for cross in ("ixy", "ixz", "iyz"):
        value = inertia.get(cross)
        _require(
            isinstance(value, (int, float)) and math.isfinite(value),
            f"{name}.{cross}必须是有限数值",
        )
    _require(ixx + iyy >= izz, f"{name}不满足ixx+iyy>=izz")
    _require(ixx + izz >= iyy, f"{name}不满足ixx+izz>=iyy")
    _require(iyy + izz >= ixx, f"{name}不满足iyy+izz>=ixx")


def validate_model(model: dict[str, Any]) -> list[str]:
    """返回验证摘要；失败时抛出ModelContractError。"""
    _require(model.get("model_version") == "m2.v1", "模型版本必须为m2.v1")
    _require(model.get("status") == "simulation_initial", "当前必须标记为仿真初值")

    frames = model.get("frames", {})
    _require(frames.get("odom") == "odom", "里程计Frame必须为odom")
    _require(frames.get("base_link") == "base_link", "机体Frame必须为base_link")
    footprint = frames.get("base_footprint", {})
    _require(
        footprint.get("parent") == "base_link",
        "base_footprint不得改变odom主TF链",
    )
    _require(
        footprint.get("role") == "ground_projection_only",
        "base_footprint只能作为地面投影辅助Frame",
    )
    _vector(footprint.get("xyz"), "base_footprint.xyz")

    chassis = model.get("chassis", {})
    geometry = chassis.get("geometry", {})
    _require(geometry.get("type") == "box", "首版底盘碰撞体必须是box")
    for field in ("length", "width", "height"):
        _positive(geometry.get(field), f"chassis.geometry.{field}")
    base_height = _positive(
        chassis.get("base_link_height"),
        "base_link_height",
    )
    _positive(chassis.get("mass"), "chassis.mass")
    _validate_inertia(chassis.get("inertia"), "chassis.inertia")

    drive = model.get("drive", {})
    _require(drive.get("type") == "differential", "驱动类型必须是differential")
    separation = _positive(drive.get("wheel_separation"), "wheel_separation")
    radius = _positive(drive.get("wheel_radius"), "wheel_radius")
    _positive(drive.get("wheel_width"), "wheel_width")
    _positive(drive.get("wheel_mass"), "wheel_mass")
    _validate_inertia(drive.get("wheel_inertia"), "wheel_inertia")
    _require(
        _vector(drive.get("joint_axis"), "joint_axis")
        == [0.0, 1.0, 0.0],
        "轮轴必须沿+y",
    )

    wheels = drive.get("wheels", {})
    left = wheels.get("left", {})
    right = wheels.get("right", {})
    for side, wheel in (("left", left), ("right", right)):
        _require(
            wheel.get("parent") == "base_link",
            f"{side}轮父Frame必须为base_link",
        )
        _require(
            wheel.get("link_name") == f"{side}_wheel_link",
            f"{side}轮Link名称错误",
        )
        _require(
            wheel.get("joint_name") == f"{side}_wheel_joint",
            f"{side}轮Joint名称错误",
        )
    left_xyz = _vector(left.get("xyz"), "left_wheel.xyz")
    right_xyz = _vector(right.get("xyz"), "right_wheel.xyz")
    _require(left_xyz[0] == right_xyz[0], "左右轮x位置必须一致")
    _require(
        left_xyz[1] == -right_xyz[1] and left_xyz[1] > 0,
        "左右轮必须关于x轴对称",
    )
    _require(left_xyz[2] == right_xyz[2], "左右轮z位置必须一致")
    _require(math.isclose(left_xyz[1] - right_xyz[1], separation), "轮位置必须匹配轮距")
    _require(math.isclose(base_height + left_xyz[2], radius), "轮心高度必须匹配轮半径")

    casters = model.get("casters", {})
    _require(casters.get("geometry") == "sphere", "首版万向轮碰撞体必须是sphere")
    _positive(casters.get("radius"), "caster.radius")
    _positive(casters.get("mass_each"), "caster.mass_each")
    _validate_inertia(casters.get("inertia_each"), "caster.inertia_each")
    items = casters.get("items")
    _require(
        isinstance(items, list) and len(items) == 2,
        "首版必须定义前后两个支撑球",
    )

    limits = model.get("limits", {})
    for group in ("linear_x", "angular_z"):
        _positive(
            limits.get(group, {}).get("max_velocity"),
            f"{group}.max_velocity",
        )
        _positive(
            limits.get(group, {}).get("max_acceleration"),
            f"{group}.max_acceleration",
        )

    control = model.get("control", {})
    _require(control.get("cmd_vel_timeout_sec") == 0.2, "速度命令超时必须为0.2 s")
    _require(control.get("use_stamped_vel") is False, "M1 Twist接口要求非时间戳模式")
    _require(control.get("position_feedback") is True, "里程计必须使用轮位置反馈")
    _require(control.get("open_loop") is False, "M2不得使用开环里程计")
    _require(control.get("enable_odom_tf") is True, "差速控制器必须发布odom TF")
    _require(control.get("odom_frame_id") == "odom", "odom_frame_id错误")
    _require(control.get("base_frame_id") == "base_link", "base_frame_id错误")
    _positive(control.get("update_rate_hz"), "control.update_rate_hz")
    odom_rate = _positive(
        control.get("odom_publish_rate_hz"),
        "control.odom_publish_rate_hz",
    )
    _require(odom_rate >= 20.0, "里程计发布频率不得低于20 Hz")

    simulation = model.get("simulation", {})
    _require(simulation.get("use_sim_time") is True, "仿真必须使用use_sim_time")
    _positive(simulation.get("gravity_mps2"), "simulation.gravity_mps2")

    return [
        "底盘、车轮、支撑球质量和惯量有效",
        "左右轮位置、轮距、轮半径和轴向一致",
        "odom -> base_link主TF链及辅助base_footprint边界有效",
        "速度限制、0.2 s超时和闭环里程计策略有效",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "model",
        nargs="?",
        type=Path,
        default=Path("config/common/robot_model.yaml"),
    )
    args = parser.parse_args()
    try:
        summary = validate_model(load_model(args.model))
    except (OSError, yaml.YAMLError, ModelContractError) as error:
        print(f"机器人模型参数检查失败：{error}")
        return 1
    print(f"机器人模型参数检查通过：{args.model}")
    for item in summary:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
