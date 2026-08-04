#!/usr/bin/env python3
"""在隔离的M2仿真中验证差速控制器限速、超时和异常输入行为。"""

import argparse
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node


class SafetyCheck(Node):
    def __init__(self):
        super().__init__('m2_w7_safety_check')
        self.publisher = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.samples = []
        self.create_subscription(Odometry, '/robot/odom', self._on_odom, 10)

    def _on_odom(self, message):
        self.samples.append((
            message.header.stamp.sec + message.header.stamp.nanosec * 1e-9,
            message.twist.twist.linear.x,
            message.twist.twist.angular.z,
        ))

    def spin_for(self, duration, command=None, rate_hz=50.0):
        if not self.samples:
            rclpy.spin_once(self, timeout_sec=1.0)
        if not self.samples:
            raise RuntimeError('等待场景首个里程计样本超时')
        start = self.samples[-1][0]
        wall_deadline = time.monotonic() + max(10.0, duration * 10.0)
        period = 1.0 / rate_hz
        while self.samples[-1][0] - start < duration:
            if time.monotonic() >= wall_deadline:
                raise RuntimeError(f'仿真时间在{duration:.1f} s场景中停止推进')
            if command is not None:
                self.publisher.publish(command)
            rclpy.spin_once(self, timeout_sec=period)

    def command(self, linear=0.0, angular=0.0):
        message = Twist()
        message.linear.x = linear
        message.angular.z = angular
        return message


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _max_slope(samples, value_index):
    slopes = []
    for previous, current in zip(samples, samples[1:]):
        dt = current[0] - previous[0]
        if dt >= 0.005:
            slopes.append(abs(current[value_index] - previous[value_index]) / dt)
    return max(slopes, default=0.0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--startup-timeout', type=float, default=20.0)
    args = parser.parse_args()

    rclpy.init()
    node = SafetyCheck()
    try:
        deadline = time.monotonic() + args.startup_timeout
        while not node.samples and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        _require(node.samples, '等待/robot/odom超时')

        node.spin_for(0.8, node.command())
        node.samples.clear()
        node.spin_for(1.2, node.command(linear=2.0))
        linear_samples = list(node.samples)
        linear_peak = max(abs(item[1]) for item in linear_samples)
        linear_slope = _max_slope(linear_samples, 1)
        _require(0.50 <= linear_peak <= 0.63,
                 f'线速度限制异常：峰值{linear_peak:.3f} m/s')
        _require(linear_slope <= 1.30,
                 f'线加速度限制异常：最大斜率{linear_slope:.3f} m/s^2')

        timeout_start = node.samples[-1][0]
        node.samples.clear()
        node.spin_for(1.1)
        timeout_samples = list(node.samples)
        early = [abs(item[1]) for item in timeout_samples
                 if 0.10 <= item[0] - timeout_start <= 0.18]
        late = [abs(item[1]) for item in timeout_samples
                if item[0] - timeout_start >= 0.95]
        _require(early and min(early) >= 0.45,
                 '命令在0.2 s超时窗口前过早衰减')
        _require(late and max(late) <= 0.03,
                 '命令超时后未按加速度限制停车')

        node.samples.clear()
        node.spin_for(0.9, node.command(angular=5.0))
        angular_samples = list(node.samples)
        angular_peak = max(abs(item[2]) for item in angular_samples)
        angular_slope = _max_slope(angular_samples, 2)
        _require(1.30 <= angular_peak <= 1.58,
                 f'角速度限制异常：峰值{angular_peak:.3f} rad/s')
        _require(angular_slope <= 3.60,
                 f'角加速度限制异常：最大斜率{angular_slope:.3f} rad/s^2')
        node.spin_for(0.9, node.command())

        invalid_samples = []
        for invalid_value in (math.nan, math.inf, -math.inf):
            node.samples.clear()
            node.spin_for(0.12, node.command(linear=invalid_value))
            node.spin_for(0.25)
            invalid_samples.extend(node.samples)
        finite_after_invalid = all(
            math.isfinite(item[1]) and math.isfinite(item[2])
            for item in invalid_samples
        )
        _require(finite_after_invalid,
                 'NaN或Infinity输入导致里程计出现非有限数值')

        node.samples.clear()
        node.spin_for(0.7, node.command(linear=0.2))
        recovery_peak = max((item[1] for item in node.samples), default=0.0)
        _require(0.12 <= recovery_peak <= 0.23,
                 f'异常输入后恢复失败：峰值{recovery_peak:.3f} m/s')
        node.spin_for(0.7, node.command())

        print('M2-W7运行安全检查通过')
        print(f'- 线速度峰值：{linear_peak:.3f} m/s（限制0.6）')
        print(f'- 线加速度最大采样斜率：{linear_slope:.3f} m/s^2（限制1.0）')
        print('- 停止命令发布后：0.2 s窗口内保持，随后减速并停车')
        print(f'- 角速度峰值：{angular_peak:.3f} rad/s（限制1.5）')
        print(f'- 角加速度最大采样斜率：{angular_slope:.3f} rad/s^2（限制3.0）')
        print('- NaN、Infinity输入被安全处理，后续合法命令恢复成功')
        return 0
    except RuntimeError as error:
        print(f'M2-W7运行安全检查失败：{error}')
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
