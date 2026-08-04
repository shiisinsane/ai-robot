#!/usr/bin/env python3
"""运行时验证M3雷达频率、几何、Frame和固定障碍物距离。"""

import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan


class LidarCheck(Node):
    def __init__(self) -> None:
        super().__init__('m3_lidar_check')
        self.samples: list[tuple[float, LaserScan]] = []
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )
        self.subscription = self.create_subscription(
            LaserScan,
            '/robot/scan',
            lambda message: self.samples.append((time.monotonic(), message)),
            qos,
        )


def _range_at(message: LaserScan, angle: float) -> float:
    index = round((angle - message.angle_min) / message.angle_increment)
    return float(message.ranges[index])


def main() -> int:
    rclpy.init()
    node = LidarCheck()
    start = time.monotonic()
    try:
        while len(node.samples) < 40 and time.monotonic() - start < 15.0:
            rclpy.spin_once(node, timeout_sec=0.2)
        if len(node.samples) < 20:
            raise RuntimeError(f'15秒内只收到{len(node.samples)}帧扫描')

        message = node.samples[-1][1]
        wall_rate = (len(node.samples) - 1) / (
            node.samples[-1][0] - node.samples[0][0]
        )
        stamps = [
            item.header.stamp.sec + item.header.stamp.nanosec / 1e9
            for _, item in node.samples
        ]
        stamp_rate = (len(stamps) - 1) / (stamps[-1] - stamps[0])
        front = _range_at(message, 0.0)
        left = _range_at(message, math.pi / 2.0)

        if message.header.frame_id != 'laser_link':
            raise RuntimeError(f'Frame错误：{message.header.frame_id}')
        if len(message.ranges) != 360:
            raise RuntimeError(f'扫描点数错误：{len(message.ranges)}')
        if not math.isclose(message.angle_min, -math.pi, abs_tol=1e-5):
            raise RuntimeError(f'最小角错误：{message.angle_min}')
        if not math.isclose(message.angle_max, math.pi, abs_tol=1e-5):
            raise RuntimeError(f'最大角错误：{message.angle_max}')
        if not math.isclose(message.range_min, 0.12, abs_tol=1e-5):
            raise RuntimeError(f'最小量程错误：{message.range_min}')
        if not math.isclose(message.range_max, 8.0, abs_tol=1e-5):
            raise RuntimeError(f'最大量程错误：{message.range_max}')
        if wall_rate < 10.0:
            raise RuntimeError(f'墙钟接收频率不足：{wall_rate:.3f} Hz')
        if not 1.70 <= front <= 1.80:
            raise RuntimeError(f'前方障碍距离错误：{front:.3f} m')
        if not 2.20 <= left <= 2.30:
            raise RuntimeError(f'左侧障碍距离错误：{left:.3f} m')

        print('M3激光雷达运行检查通过')
        print(f'- 消息数：{len(node.samples)}')
        print(f'- 墙钟/仿真时间频率：{wall_rate:.3f}/{stamp_rate:.3f} Hz')
        print(f'- Frame/点数：{message.header.frame_id}/{len(message.ranges)}')
        print(f'- 前方/左侧障碍距离：{front:.3f}/{left:.3f} m')
        return 0
    except RuntimeError as error:
        print(f'M3激光雷达运行检查失败：{error}')
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
