#!/usr/bin/env python3
"""量化AMCL位姿输出、静止抖动和map到odom TF。"""

import argparse
import math
import statistics
import time
import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from rclpy.node import Node
from tf2_ros import Buffer, TransformListener


class Check(Node):
    def __init__(self):
        super().__init__('m5_localization_check')
        self.samples = []
        self.tf_samples = []
        self.initialpose = self.create_publisher(
            PoseWithCovarianceStamped, '/robot/initialpose', 10)
        self.create_subscription(PoseWithCovarianceStamped, '/robot/pose',
                                 self.samples.append, 10)
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=10.0)
    args = parser.parse_args()
    rclpy.init()
    node = Check()
    initial = PoseWithCovarianceStamped()
    initial.header.frame_id = 'map'
    initial.pose.pose.orientation.w = 1.0
    initial.pose.covariance[0] = 0.04
    initial.pose.covariance[7] = 0.04
    initial.pose.covariance[35] = 0.02
    start_wait = time.monotonic() + 1.0
    while time.monotonic() < start_wait:
        rclpy.spin_once(node, timeout_sec=0.1)
    publish_until = time.monotonic() + 1.0
    while time.monotonic() < publish_until:
        node.initialpose.publish(initial)
        rclpy.spin_once(node, timeout_sec=0.1)
    end = time.monotonic() + args.duration
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
        try:
            transform = node.buffer.lookup_transform('map', 'base_link', rclpy.time.Time())
            node.tf_samples.append((transform.transform.translation.x,
                                    transform.transform.translation.y))
        except Exception:
            pass
    errors = []
    if not node.samples:
        errors.append('AMCL位姿样本不足')
    if len(node.tf_samples) < 10:
        errors.append('定位TF样本不足')
        jitter = math.inf
    else:
        xs = [item[0] for item in node.tf_samples]
        ys = [item[1] for item in node.tf_samples]
        jitter = math.hypot(statistics.pstdev(xs), statistics.pstdev(ys))
        if jitter > 0.03:
            errors.append(f'静止位置抖动{jitter:.4f} m超过0.03 m')
    if not node.buffer.can_transform('map', 'odom', rclpy.time.Time()):
        errors.append('缺少AMCL发布的map到odom TF')
    if errors:
        print('M5-W5定位检查失败：' + '；'.join(errors)); result = 1
    else:
        print(f'M5-W5定位检查通过：位姿{len(node.samples)}条、TF {len(node.tf_samples)}条，'
              f'静止位置抖动{jitter:.4f} m')
        result = 0
    node.destroy_node(); rclpy.shutdown(); return result


if __name__ == '__main__':
    raise SystemExit(main())
