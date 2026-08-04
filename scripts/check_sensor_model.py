#!/usr/bin/env python3
"""验证M3传感器参数、接口和静态TF基线。"""

import argparse
import math
from pathlib import Path
from typing import Any

import yaml


class SensorContractError(ValueError):
    """传感器参数不满足M3基线。"""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SensorContractError(message)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise SensorContractError(f"{path}顶层必须是YAML映射")
    return value


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    _require(
        isinstance(value, (int, float)) and math.isfinite(value),
        f"{name}必须是有限数值",
    )
    number = float(value)
    if positive:
        _require(number > 0.0, f"{name}必须为正数")
    return number


def _vector(value: Any, name: str, size: int = 3) -> list[float]:
    _require(isinstance(value, list) and len(value) == size, f"{name}必须有{size}项")
    return [_number(item, name) for item in value]


def _topic_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    topics = contract.get("topics")
    _require(isinstance(topics, list), "接口契约topics必须是列表")
    return {topic["name"]: topic for topic in topics}


def _validate_interface(
    item: dict[str, Any],
    topic_key: str,
    type_key: str,
    contract_topics: dict[str, dict[str, Any]],
    rate: float,
) -> None:
    name = item.get(topic_key)
    _require(name in contract_topics, f"接口契约缺少{name}")
    contract = contract_topics[name]
    _require(item.get(type_key) == contract.get("type"), f"{name}消息类型不一致")
    _require(item.get("qos_profile") == contract.get("qos_profile"), f"{name} QoS不一致")
    _require(rate >= float(contract.get("min_rate_hz", 0.0)), f"{name}频率低于接口契约")


def _validate_mount(item: dict[str, Any], name: str) -> None:
    _require(item.get("parent") == "base_link", f"{name}必须挂在base_link")
    _require(str(item.get("link_name", "")).endswith("_link"), f"{name} Link命名错误")
    _require(str(item.get("joint_name", "")).endswith("_joint"), f"{name} Joint命名错误")
    _vector(item.get("xyz"), f"{name}.xyz")
    _vector(item.get("rpy"), f"{name}.rpy")


def _validate_covariance(value: Any, name: str, expected_variance: float) -> None:
    covariance = _vector(value, name, 9)
    diagonal = [covariance[index] for index in (0, 4, 8)]
    off_diagonal = [value for index, value in enumerate(covariance) if index not in (0, 4, 8)]
    _require(all(math.isclose(value, expected_variance) for value in diagonal), f"{name}对角值错误")
    _require(all(value == 0.0 for value in off_diagonal), f"{name}非对角值必须为零")


def validate_sensor_model(
    sensors: dict[str, Any],
    contract: dict[str, Any],
    robot: dict[str, Any],
) -> list[str]:
    _require(sensors.get("sensor_model_version") == "m3.v1", "传感器版本必须为m3.v1")
    _require(sensors.get("status") == "simulation_initial", "当前必须标记为仿真初值")
    rules = sensors.get("rules", {})
    _require(rules.get("parent_frame") == "base_link", "传感器根Frame必须是base_link")
    _require(rules.get("use_sim_time") is True, "仿真传感器必须使用仿真时间")
    _require(rules.get("bridge_direction") == "gz_to_ros", "传感器桥接必须只允许gz_to_ros")
    _require(rules.get("frame_convention") == "rep_103", "坐标约定必须为REP-103")

    topics = _topic_map(contract)
    lidar = sensors.get("lidar", {})
    camera = sensors.get("camera", {})
    imu = sensors.get("imu", {})
    for name, item in (("lidar", lidar), ("camera", camera), ("imu", imu)):
        _require(item.get("enabled") is True, f"{name}必须启用")
        _validate_mount(item, name)

    links = {lidar["link_name"], camera["link_name"], imu["link_name"]}
    optical = camera.get("optical_frame", {})
    _require(optical.get("parent") == camera.get("link_name"), "相机optical frame父级错误")
    _require(optical.get("link_name") == "camera_color_optical_frame", "相机optical frame名称错误")
    _require(
        _vector(optical.get("rpy"), "camera.optical_frame.rpy")
        == [-1.570796327, 0.0, -1.570796327],
        "相机optical frame旋转不符合REP-103",
    )
    _require(optical["link_name"] not in links, "传感器Frame必须唯一")

    chassis = robot.get("chassis", {}).get("geometry", {})
    half_length = _number(chassis.get("length"), "chassis.length", positive=True) / 2.0
    half_width = _number(chassis.get("width"), "chassis.width", positive=True) / 2.0
    for name, item in (("lidar", lidar), ("camera", camera), ("imu", imu)):
        x, y, _ = _vector(item["xyz"], f"{name}.xyz")
        _require(abs(x) <= half_length and abs(y) <= half_width, f"{name}安装点超出底盘平面")

    lidar_rate = _number(lidar.get("update_rate_hz"), "lidar.update_rate_hz", positive=True)
    _validate_interface(lidar, "topic", "message_type", topics, lidar_rate)
    horizontal = lidar.get("horizontal", {})
    _require(isinstance(horizontal.get("samples"), int) and horizontal["samples"] >= 360, "雷达采样数不得低于360")
    min_angle = _number(horizontal.get("min_angle"), "lidar.min_angle")
    max_angle = _number(horizontal.get("max_angle"), "lidar.max_angle")
    _require(min_angle < 0.0 < max_angle and math.isclose(max_angle - min_angle, 2 * math.pi, rel_tol=1e-6), "雷达必须覆盖360度")
    ranges = lidar.get("range", {})
    range_min = _number(ranges.get("min"), "lidar.range.min", positive=True)
    range_max = _number(ranges.get("max"), "lidar.range.max", positive=True)
    _require(range_max > range_min, "雷达最大量程必须大于最小量程")
    housing = lidar.get("housing", {})
    for field in ("radius", "height", "mass"):
        _number(housing.get(field), f"lidar.housing.{field}", positive=True)
    inertia = housing.get("inertia", {})
    for field in ("ixx", "iyy", "izz"):
        _number(inertia.get(field), f"lidar.housing.inertia.{field}", positive=True)

    camera_rate = _number(camera.get("update_rate_hz"), "camera.update_rate_hz", positive=True)
    _validate_interface(camera, "image_topic", "image_type", topics, camera_rate)
    camera_info = dict(camera)
    camera_info["qos_profile"] = camera.get("qos_profile")
    _validate_interface(camera_info, "camera_info_topic", "camera_info_type", topics, camera_rate)
    image = camera.get("image", {})
    _require(image.get("width") == 640 and image.get("height") == 480, "首版相机必须为640x480")
    _require(image.get("format") == "R8G8B8" and image.get("ros_encoding") == "rgb8", "相机编码必须为RGB8")
    clip = camera.get("clip", {})
    _require(_number(clip.get("far"), "camera.clip.far", positive=True) > _number(clip.get("near"), "camera.clip.near", positive=True), "相机远裁剪面必须大于近裁剪面")
    _require(camera.get("depth_interface_enabled") is False, "M3首版不得启用深度相机接口")
    housing = camera.get("housing", {})
    _vector(housing.get("size"), "camera.housing.size")
    _number(housing.get("mass"), "camera.housing.mass", positive=True)
    for field in ("ixx", "iyy", "izz"):
        _number(housing.get("inertia", {}).get(field), f"camera.housing.inertia.{field}", positive=True)

    imu_rate = _number(imu.get("update_rate_hz"), "imu.update_rate_hz", positive=True)
    _validate_interface(imu, "topic", "message_type", topics, imu_rate)
    angular_stddev = _number(imu.get("angular_velocity_noise_stddev"), "imu.angular_noise", positive=True)
    linear_stddev = _number(imu.get("linear_acceleration_noise_stddev"), "imu.linear_noise", positive=True)
    covariance = imu.get("covariance", {})
    _validate_covariance(covariance.get("angular_velocity"), "imu.angular_covariance", angular_stddev**2)
    _validate_covariance(covariance.get("linear_acceleration"), "imu.linear_covariance", linear_stddev**2)
    _validate_covariance(covariance.get("orientation"), "imu.orientation_covariance", 0.0001)

    encoder = sensors.get("encoder", {})
    _validate_interface(encoder, "source_topic", "message_type", topics, _number(encoder.get("min_update_rate_hz"), "encoder.min_rate", positive=True))
    _require(encoder.get("left_joint") == robot["drive"]["wheels"]["left"]["joint_name"], "左编码器关节不匹配")
    _require(encoder.get("right_joint") == robot["drive"]["wheels"]["right"]["joint_name"], "右编码器关节不匹配")

    return [
        "雷达、相机、IMU安装Frame唯一且符合REP-103",
        "传感器Topic、消息、QoS和频率满足m1.v1契约",
        "雷达量程、相机成像和IMU噪声协方差参数有效",
        "编码器关节、方向、单位和最低频率映射M2底盘",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sensors", type=Path, default=Path("config/common/sensor_model.yaml"))
    parser.add_argument("--contract", type=Path, default=Path("config/common/interface_contract.yaml"))
    parser.add_argument("--robot", type=Path, default=Path("config/common/robot_model.yaml"))
    args = parser.parse_args()
    try:
        summary = validate_sensor_model(load_yaml(args.sensors), load_yaml(args.contract), load_yaml(args.robot))
    except (OSError, yaml.YAMLError, SensorContractError) as error:
        print(f"传感器参数检查失败：{error}")
        return 1
    print(f"传感器参数检查通过：{args.sensors}")
    for item in summary:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
