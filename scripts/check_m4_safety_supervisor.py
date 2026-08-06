#!/usr/bin/env python3
"""运行验证M4-W7安全监督、锁存、清除和故障隔离。"""

import argparse
import threading
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool
from std_srvs.srv import Trigger


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


class SafetyCheck(Node):
    def __init__(self):
        super().__init__('m4_w7_safety_check')
        latched = QoSProfile(
            depth=1, reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.stop = []
        self.codes = []
        self.velocity = []
        self.publisher = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.create_subscription(
            Bool, '/robot/safety/stop_active',
            lambda msg: self.stop.append((time.monotonic(), msg.data)), latched)
        self.create_subscription(
            DiagnosticArray, '/robot/diagnostics', self._on_diagnostics, 10)
        self.create_subscription(
            Odometry, '/robot/odom',
            lambda msg: self.velocity.append(
                (time.monotonic(), msg.twist.twist.linear.x)), 10)
        self.client = self.create_client(Trigger, '/robot/safety/clear_faults')

    def _on_diagnostics(self, message):
        for status in message.status:
            if status.name == 'safety_supervisor':
                values = {item.key: item.value for item in status.values}
                level = status.level[0] if isinstance(status.level, bytes) else status.level
                self.codes.append((time.monotonic(), level, values.get('code', '')))

    def spin_for(self, duration, command=None):
        stop_publisher = threading.Event()
        thread = None
        if command is not None:
            def publish_loop():
                while not stop_publisher.wait(0.02):
                    self.publisher.publish(command)
            self.publisher.publish(command)
            thread = threading.Thread(target=publish_loop, daemon=True)
            thread.start()
        deadline = time.monotonic() + duration
        try:
            while time.monotonic() < deadline:
                rclpy.spin_once(self, timeout_sec=0.04)
        finally:
            stop_publisher.set()
            if thread is not None:
                thread.join(timeout=0.2)

    def wait_ready(self):
        deadline = time.monotonic() + 30.0
        while (not self.stop or not self.velocity or not self.client.service_is_ready()):
            _require(time.monotonic() < deadline, '等待安全监督器、里程计或清除服务超时')
            rclpy.spin_once(self, timeout_sec=0.1)

    def clear_while_zero(self):
        zero = Twist()
        self.spin_for(0.3, zero)
        future = self.client.call_async(Trigger.Request())
        deadline = time.monotonic() + 2.0
        while not future.done():
            _require(time.monotonic() < deadline, '调用故障清除服务超时')
            self.publisher.publish(zero)
            rclpy.spin_once(self, timeout_sec=0.04)
        return future.result()


def _normal(node):
    result = node.clear_while_zero()
    _require(result.success, result.message)
    node.stop.clear()
    motion = Twist()
    motion.linear.x = 0.15
    node.spin_for(1.0, motion)
    _require(any(not active for _, active in node.stop), '健康状态下安全停车未解除')
    _require(max((abs(value) for _, value in node.velocity[-80:]), default=0.0) > 0.05,
             '健康命令未驱动车体')

    fault_start = time.monotonic()
    node.spin_for(0.8)
    _require(any(active for stamp, active in node.stop if stamp >= fault_start),
             '命令超时后未激活安全停车')
    _require(any('command_timeout' in code for _, _, code in node.codes),
             '诊断未报告command_timeout')
    _require(abs(node.velocity[-1][1]) < 0.03, '命令超时后机器人未停车')

    failed = node.client.call_async(Trigger.Request())
    rclpy.spin_until_future_complete(node, failed, timeout_sec=1.0)
    _require(failed.done() and not failed.result().success,
             '没有新鲜零速度命令时不应允许清除锁存')
    result = node.clear_while_zero()
    _require(result.success, result.message)
    node.spin_for(0.2, Twist())
    _require(node.stop and not node.stop[-1][1], '满足条件后故障未解除')

    invalid = Twist()
    invalid.linear.x = float('nan')
    node.publisher.publish(invalid)
    node.spin_for(0.2, Twist())
    _require(any('invalid_command' in code for _, _, code in node.codes),
             '非有限速度命令未报告invalid_command')
    _require(node.stop and node.stop[-1][1], '非有限速度命令未锁存停车')
    result = node.clear_while_zero()
    _require(result.success, result.message)
    print('M4-W7正常、命令超时、非有限命令、锁存和清除验证通过')


def _scan_fault(node):
    motion = Twist()
    motion.linear.x = 0.15
    node.spin_for(1.0, motion)
    _require(node.stop and node.stop[-1][1], '雷达缺失时未保持安全停车')
    _require(any('scan_timeout' in code for _, _, code in node.codes),
             '诊断未锁存scan_timeout')
    _require(max((abs(value) for _, value in node.velocity[-50:]), default=0.0) < 0.03,
             '雷达缺失时机器人发生运动')
    result = node.clear_while_zero()
    _require(not result.success, '雷达未恢复时不应允许清除故障')
    print('M4-W7雷达断流、拒绝运动和拒绝清除验证通过')


def _camera_warning(node):
    result = node.clear_while_zero()
    _require(result.success, result.message)
    node.codes.clear()
    motion = Twist()
    motion.linear.x = 0.15
    node.spin_for(1.0, motion)
    _require(any(code == 'camera_timeout' and level == 1
                 for _, level, code in node.codes),
             '相机超时未产生WARN诊断')
    _require(node.stop and not node.stop[-1][1], '相机告警错误触发安全停车')
    _require(max((abs(value) for _, value in node.velocity[-80:]), default=0.0) > 0.05,
             '相机告警错误阻断机器人运动')
    node.spin_for(0.4, Twist())
    print('M4-W7相机超时仅告警、不停车验证通过')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', choices=('normal', 'scan', 'camera'), default='normal')
    args = parser.parse_args()
    rclpy.init()
    node = SafetyCheck()
    try:
        node.wait_ready()
        {'normal': _normal, 'scan': _scan_fault, 'camera': _camera_warning}[args.scenario](node)
    finally:
        node.publisher.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
