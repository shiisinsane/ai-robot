#!/usr/bin/env python3
"""检查M5-W3运行期地图、雷达、里程计和TF主链。"""

import argparse
import time

import rclpy
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformListener


class SlamCheck(Node):
    def __init__(self):
        super().__init__('m5_slam_runtime_check')
        map_qos = QoSProfile(
            depth=1, reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL)
        sensor_qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.maps = []
        self.scan_count = 0
        self.odom_count = 0
        self.create_subscription(OccupancyGrid, '/robot/map', self.maps.append, map_qos)
        self.create_subscription(
            LaserScan, '/robot/scan', lambda _: setattr(self, 'scan_count', self.scan_count + 1),
            sensor_qos)
        self.create_subscription(
            Odometry, '/robot/odom', lambda _: setattr(self, 'odom_count', self.odom_count + 1), 10)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=6.0)
    args = parser.parse_args()
    rclpy.init()
    node = SlamCheck()
    deadline = time.monotonic() + args.duration
    while rclpy.ok() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    errors = []
    if not node.maps:
        errors.append('未收到/robot/map')
    else:
        grid = node.maps[-1]
        occupied = sum(value >= 65 for value in grid.data)
        free = sum(value == 0 for value in grid.data)
        if grid.info.resolution > 0.050001:
            errors.append('地图分辨率高于0.05 m')
        if grid.info.width < 100 or grid.info.height < 100:
            errors.append('地图覆盖范围不足')
        if occupied < 100 or free < 1000:
            errors.append('地图占用或自由栅格不足')
    if node.scan_count < args.duration * 8:
        errors.append('雷达频率低于8 Hz')
    if node.odom_count < args.duration * 15:
        errors.append('融合里程计频率低于15 Hz')
    for parent, child in (('map', 'odom'), ('odom', 'base_link'), ('base_link', 'laser_link')):
        if not node.tf_buffer.can_transform(parent, child, rclpy.time.Time()):
            errors.append(f'缺少{parent}到{child} TF')
    if errors:
        print('M5-W3运行检查失败：' + '；'.join(errors))
        result = 1
    else:
        grid = node.maps[-1]
        occupied = sum(value >= 65 for value in grid.data)
        free = sum(value == 0 for value in grid.data)
        print('M5-W3运行检查通过')
        print(f'- 地图：{grid.info.width}x{grid.info.height}，分辨率{grid.info.resolution:.3f} m，'
              f'占用{occupied}格，自由{free}格')
        print(f'- {args.duration:.1f}秒内雷达{node.scan_count}条，融合里程计{node.odom_count}条')
        print('- TF主链map→odom→base_link及base_link→laser_link完整')
        result = 0
    node.destroy_node()
    rclpy.shutdown()
    return result


if __name__ == '__main__':
    raise SystemExit(main())
