#!/usr/bin/env python3
"""验证M2前进、后退、转向、停车、轮状态和TF方向。"""

import math
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import JointState
from tf2_msgs.msg import TFMessage


class MotionCheck(Node):
    def __init__(self):
        super().__init__('m2_motion_check')
        self.odom = []
        self.joints = []
        self.tf_edges = set()
        self.publisher = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.create_subscription(Odometry, '/robot/odom', self._on_odom, 10)
        self.create_subscription(
            JointState, '/robot/joint_states', self._on_joints, 10)
        self.create_subscription(TFMessage, '/tf', self._on_tf, 100)

    def _on_odom(self, message):
        stamp = message.header.stamp
        self.odom.append((
            stamp.sec + stamp.nanosec * 1e-9,
            message.twist.twist.linear.x,
            message.twist.twist.angular.z,
            message.header.frame_id,
            message.child_frame_id,
        ))

    def _on_joints(self, message):
        velocities = dict(zip(message.name, message.velocity))
        self.joints.append(velocities)

    def _on_tf(self, message):
        for transform in message.transforms:
            self.tf_edges.add((
                transform.header.frame_id,
                transform.child_frame_id,
            ))

    def command(self, linear=0.0, angular=0.0):
        message = Twist()
        message.linear.x = linear
        message.angular.z = angular
        return message

    def run_for(self, duration, command):
        if not self.odom:
            rclpy.spin_once(self, timeout_sec=1.0)
        _require(self.odom, '等待里程计超时')
        start = self.odom[-1][0]
        deadline = time.monotonic() + max(10.0, duration * 10.0)
        while self.odom[-1][0] - start < duration:
            _require(time.monotonic() < deadline, '仿真时间停止推进')
            self.publisher.publish(command)
            rclpy.spin_once(self, timeout_sec=0.02)


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _wheel_pair(samples):
    for sample in reversed(samples):
        if {'left_wheel_joint', 'right_wheel_joint'} <= sample.keys():
            return sample['left_wheel_joint'], sample['right_wheel_joint']
    raise RuntimeError('关节状态缺少左右轮')


def _check_phase(node, command, expected_linear=0, expected_angular=0):
    node.run_for(0.8, command)
    linear = node.odom[-1][1]
    angular = node.odom[-1][2]
    left, right = _wheel_pair(node.joints)
    if expected_linear:
        _require(math.copysign(1, linear) == expected_linear,
                 f'线速度方向错误：{linear:.3f}')
        _require(math.copysign(1, left) == expected_linear and
                 math.copysign(1, right) == expected_linear,
                 f'左右轮方向错误：{left:.3f}, {right:.3f}')
    if expected_angular:
        _require(math.copysign(1, angular) == expected_angular,
                 f'角速度方向错误：{angular:.3f}')
        _require(math.copysign(1, left) == -expected_angular and
                 math.copysign(1, right) == expected_angular,
                 f'转向轮速方向错误：{left:.3f}, {right:.3f}')


def main():
    rclpy.init()
    node = MotionCheck()
    try:
        deadline = time.monotonic() + 20.0
        while (not node.odom or not node.joints or
               ('odom', 'base_link') not in node.tf_edges):
            _require(time.monotonic() < deadline, '等待运动状态或TF超时')
            rclpy.spin_once(node, timeout_sec=0.1)

        _check_phase(node, node.command(linear=0.25), expected_linear=1)
        _check_phase(node, node.command(linear=-0.25), expected_linear=-1)
        _check_phase(node, node.command(angular=0.8), expected_angular=1)
        _check_phase(node, node.command(angular=-0.8), expected_angular=-1)
        node.run_for(0.8, node.command())
        _require(abs(node.odom[-1][1]) <= 0.02 and
                 abs(node.odom[-1][2]) <= 0.02,
                 '零速命令后未停车')
        _require(all(item[3:] == ('odom', 'base_link') for item in node.odom),
                 '里程计Frame不符合odom → base_link契约')
        print('M2运动、轮状态、停车和TF场景检查通过')
        return 0
    except RuntimeError as error:
        print(f'M2运动场景检查失败：{error}')
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
