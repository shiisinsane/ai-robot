#!/usr/bin/env python3
"""将Gazebo作用域扫描规范化为M1公共雷达接口。"""

import copy

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan


SENSOR_QOS = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
    reliability=ReliabilityPolicy.BEST_EFFORT,
)


def normalize_scan(message: LaserScan, frame_id: str) -> LaserScan:
    """复制扫描并将实现相关Frame替换为公共Frame。"""
    normalized = copy.deepcopy(message)
    normalized.header.frame_id = frame_id
    return normalized


class ScanAdapter(Node):
    """保持扫描数据与时间戳不变，只规范化公共Frame和QoS。"""

    def __init__(self) -> None:
        super().__init__('lidar_driver')
        self.declare_parameter('frame_id', 'laser_link')
        self._frame_id = self.get_parameter('frame_id').value
        self._publisher = self.create_publisher(LaserScan, 'scan', SENSOR_QOS)
        self._subscription = self.create_subscription(
            LaserScan,
            'scan_raw',
            self._on_scan,
            SENSOR_QOS,
        )

    def _on_scan(self, message: LaserScan) -> None:
        self._publisher.publish(normalize_scan(message, self._frame_id))


def main() -> None:
    rclpy.init()
    node = ScanAdapter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
