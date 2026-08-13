"""M6到点感知快照的无ROS通信判定逻辑。"""

import math


def stamp_seconds(stamp):
    """把ROS消息时间戳转换为秒。"""
    return float(stamp.sec) + float(stamp.nanosec) / 1e9


def message_age(now_seconds, message):
    """返回消息相对当前ROS时间的年龄；未来时间戳也视为无效。"""
    age = now_seconds - stamp_seconds(message.header.stamp)
    return age if age >= 0.0 and math.isfinite(age) else math.inf


def classify_inputs(messages, now_seconds, freshness_sec):
    """返回(unavailable, stale)，名称顺序由调用者提供并保持稳定。"""
    unavailable = [name for name, message in messages.items() if message is None]
    stale = [name for name, message in messages.items()
             if message is not None and
             message_age(now_seconds, message) > freshness_sec]
    return unavailable, stale


def scan_metadata(message):
    """提取扫描点数和量程内的最近有限距离。"""
    valid = [float(value) for value in message.ranges
             if math.isfinite(value) and
             message.range_min <= value <= message.range_max]
    return len(message.ranges), min(valid) if valid else math.nan
