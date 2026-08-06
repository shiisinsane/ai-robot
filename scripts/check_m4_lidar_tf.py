#!/usr/bin/env python3
"""验证M4-W5运动雷达、TF空间解释以及可控断流。"""

import argparse
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformException, TransformListener


SENSOR_QOS = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
    reliability=ReliabilityPolicy.BEST_EFFORT,
)


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _yaw(orientation):
    return math.atan2(
        2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
        1.0 - 2.0 * (orientation.y ** 2 + orientation.z ** 2),
    )


def _point_in_odom(scan, transform):
    laser_yaw = _yaw(transform.transform.rotation)
    target_angle = math.atan2(
        -transform.transform.translation.y,
        1.8 - transform.transform.translation.x,
    ) - laser_yaw
    target_angle = math.atan2(math.sin(target_angle), math.cos(target_angle))
    center = round((target_angle - scan.angle_min) / scan.angle_increment)
    candidates = []
    for index in range(max(0, center - 1), min(len(scan.ranges), center + 2)):
        value = float(scan.ranges[index])
        if math.isfinite(value) and scan.range_min <= value <= scan.range_max:
            candidates.append((value, scan.angle_min + index * scan.angle_increment))
    _require(candidates, '已知红色障碍物方位窗口中没有有限距离')
    distance, angle = min(candidates)
    laser_x = distance * math.cos(angle)
    laser_y = distance * math.sin(angle)
    odom_x = (transform.transform.translation.x +
              math.cos(laser_yaw) * laser_x - math.sin(laser_yaw) * laser_y)
    odom_y = (transform.transform.translation.y +
              math.sin(laser_yaw) * laser_x + math.cos(laser_yaw) * laser_y)
    return distance, angle, odom_x, odom_y


class LidarTfCheck(Node):
    def __init__(self):
        super().__init__('m4_lidar_tf_check')
        self.scans = []
        self.odom = []
        self.create_subscription(
            LaserScan, '/robot/scan',
            lambda message: self.scans.append((time.monotonic(), message)),
            SENSOR_QOS)
        self.create_subscription(Odometry, '/robot/odom', self.odom.append, 10)
        self.publisher = self.create_publisher(Twist, '/robot/safety_cmd_vel', 10)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

    def wait_ready(self):
        deadline = time.monotonic() + 30.0
        while len(self.scans) < 20 or len(self.odom) < 20:
            _require(time.monotonic() < deadline, '等待雷达或融合里程计超时')
            rclpy.spin_once(self, timeout_sec=0.1)
        deadline = time.monotonic() + 5.0
        while not self.tf_buffer.can_transform('odom', 'laser_link', Time()):
            _require(time.monotonic() < deadline,
                     '缺少odom到base_link到laser_link完整TF链')
            rclpy.spin_once(self, timeout_sec=0.1)

    def drive(self, linear=0.0, angular=0.0, duration=1.0):
        command = Twist()
        command.linear.x = linear
        command.angular.z = angular
        stamp = self.odom[-1].header.stamp
        start = stamp.sec + stamp.nanosec * 1e-9
        deadline = time.monotonic() + 20.0
        while True:
            stamp = self.odom[-1].header.stamp
            elapsed = stamp.sec + stamp.nanosec * 1e-9 - start
            if elapsed >= duration:
                break
            _require(time.monotonic() < deadline, '运动期间仿真时间停止推进')
            self.publisher.publish(command)
            rclpy.spin_once(self, timeout_sec=0.02)
        self.publisher.publish(Twist())
        initial_count = len(self.scans)
        while len(self.scans) < initial_count + 5:
            _require(time.monotonic() < deadline, '停车后等待扫描更新超时')
            rclpy.spin_once(self, timeout_sec=0.05)

    def observation(self):
        scan = self.scans[-1][1]
        transform = self.tf_buffer.lookup_transform(
            'odom', 'laser_link', Time(), timeout=Duration(seconds=1.0))
        return scan, _point_in_odom(scan, transform)


def _normal_check(node):
    node.wait_ready()
    first_scan, initial = node.observation()
    _require(first_scan.header.frame_id == 'laser_link', '雷达Frame不是laser_link')
    _require(len(first_scan.ranges) == 360, '雷达扫描点数不是360')
    stamps = [item.header.stamp.sec + item.header.stamp.nanosec * 1e-9
              for _, item in node.scans[-20:]]
    _require(all(right > left for left, right in zip(stamps, stamps[1:])),
             '雷达时间戳不严格递增')
    sim_rate = (len(stamps) - 1) / (stamps[-1] - stamps[0])
    _require(sim_rate >= 10.0, f'雷达仿真时间频率不足：{sim_rate:.3f} Hz')
    _require(1.65 <= initial[0] <= 1.95 and abs(initial[1]) <= 0.10,
             f'初始前方障碍物语义错误：range={initial[0]:.3f}, angle={initial[1]:.3f}')
    _require(1.65 <= initial[2] <= 1.95 and abs(initial[3]) <= 0.55,
             '初始障碍物变换到odom后的坐标错误')

    node.drive(linear=-0.2, duration=1.0)
    _, backward = node.observation()
    _require(backward[0] > initial[0] + 0.12,
             '后退后障碍物在雷达坐标中的距离未正确增加')
    _require(abs(backward[2] - initial[2]) <= 0.12 and
             abs(backward[3] - initial[3]) <= 0.12,
             '后退后障碍物在odom坐标中未保持稳定')

    node.drive(angular=0.6, duration=1.0)
    _, turned = node.observation()
    _require(turned[1] < -0.30,
             f'左转后障碍物未出现在雷达右侧：angle={turned[1]:.3f}')
    _require(abs(turned[2] - initial[2]) <= 0.20 and
             abs(turned[3] - initial[3]) <= 0.20,
             '转向后障碍物在odom坐标中未保持稳定')

    print('M4-W5雷达与TF数据链验证通过')
    print(f'- 雷达仿真时间频率：{sim_rate:.3f} Hz')
    print(f'- 初始障碍：range={initial[0]:.3f} m, angle={initial[1]:.3f} rad, '
          f'odom=({initial[2]:.3f}, {initial[3]:.3f})')
    print(f'- 后退障碍：range={backward[0]:.3f} m, '
          f'odom=({backward[2]:.3f}, {backward[3]:.3f})')
    print(f'- 左转障碍：angle={turned[1]:.3f} rad, '
          f'odom=({turned[2]:.3f}, {turned[3]:.3f})')


def _timeout_check(node):
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    _require(len(node.odom) >= 20, '故障注入时融合里程计未保持运行')
    _require(not node.scans, '关闭公共雷达链后仍收到/robot/scan')
    print('M4-W5雷达断流注入验证通过')
    print(f'- 5秒窗口融合里程计消息数：{len(node.odom)}')
    print('- /robot/scan消息数：0')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect-timeout', action='store_true')
    args = parser.parse_args()
    rclpy.init()
    node = LidarTfCheck()
    try:
        if args.expect_timeout:
            _timeout_check(node)
        else:
            _normal_check(node)
        return 0
    except (RuntimeError, TransformException) as error:
        print(f'M4-W5雷达与TF数据链验证失败：{error}')
        return 1
    finally:
        node.publisher.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
