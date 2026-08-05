#!/usr/bin/env python3
"""复核仿真轮编码器方向、累计量、频率及其与里程计的关系。"""

import math
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import JointState


LEFT_JOINT = 'left_wheel_joint'
RIGHT_JOINT = 'right_wheel_joint'
WHEEL_RADIUS = 0.075
WHEEL_SEPARATION = 0.34
MIN_RATE_HZ = 20.0


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _yaw(orientation):
    return math.atan2(
        2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
        1.0 - 2.0 * (orientation.y ** 2 + orientation.z ** 2),
    )


def _angle_delta(end, start):
    return math.atan2(math.sin(end - start), math.cos(end - start))


class EncoderCheck(Node):
    def __init__(self):
        super().__init__('m3_encoder_check')
        self.joints = []
        self.odom = []
        self.publisher = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.create_subscription(
            JointState, '/robot/joint_states', self._on_joints, 10)
        self.create_subscription(Odometry, '/robot/odom', self._on_odom, 10)

    def _on_joints(self, message):
        positions = dict(zip(message.name, message.position))
        velocities = dict(zip(message.name, message.velocity))
        if LEFT_JOINT not in positions or RIGHT_JOINT not in positions:
            return
        stamp = message.header.stamp
        self.joints.append((
            stamp.sec + stamp.nanosec * 1e-9,
            positions[LEFT_JOINT], positions[RIGHT_JOINT],
            velocities.get(LEFT_JOINT), velocities.get(RIGHT_JOINT),
        ))

    def _on_odom(self, message):
        stamp = message.header.stamp
        position = message.pose.pose.position
        self.odom.append((
            stamp.sec + stamp.nanosec * 1e-9,
            position.x, position.y, _yaw(message.pose.pose.orientation),
        ))

    def wait_ready(self):
        deadline = time.monotonic() + 25.0
        while len(self.joints) < 10 or len(self.odom) < 2:
            _require(time.monotonic() < deadline, '等待编码器或里程计超时')
            rclpy.spin_once(self, timeout_sec=0.1)

    def drive(self, linear=0.0, angular=0.0, duration=1.2):
        start_joint = self.joints[-1]
        start_odom = self.odom[-1]
        command = Twist()
        command.linear.x = linear
        command.angular.z = angular
        start_time = start_odom[0]
        deadline = time.monotonic() + 15.0
        while self.odom[-1][0] - start_time < duration:
            _require(time.monotonic() < deadline, '仿真时间停止推进')
            self.publisher.publish(command)
            rclpy.spin_once(self, timeout_sec=0.02)
        self.publisher.publish(Twist())
        for _ in range(10):
            rclpy.spin_once(self, timeout_sec=0.02)
        return start_joint, self.joints[-1], start_odom, self.odom[-1]


def _check_rate(samples):
    recent = samples[-30:]
    stamps = [sample[0] for sample in recent]
    _require(all(b > a for a, b in zip(stamps, stamps[1:])),
             '编码器时间戳不严格递增')
    rate = (len(stamps) - 1) / (stamps[-1] - stamps[0])
    _require(rate >= MIN_RATE_HZ, f'编码器频率不足：{rate:.3f} Hz')
    return rate


def _deltas(result):
    start_joint, end_joint, start_odom, end_odom = result
    left = end_joint[1] - start_joint[1]
    right = end_joint[2] - start_joint[2]
    distance = math.hypot(end_odom[1] - start_odom[1],
                          end_odom[2] - start_odom[2])
    yaw = _angle_delta(end_odom[3], start_odom[3])
    return left, right, distance, yaw


def main():
    rclpy.init()
    node = EncoderCheck()
    try:
        node.wait_ready()
        rate = _check_rate(node.joints)

        left, right, odom_distance, _ = _deltas(
            node.drive(linear=0.25))
        _require(left > 0.5 and right > 0.5,
                 f'前进累计方向错误：left={left:.3f}, right={right:.3f}')
        _require(abs(left - right) <= 0.15 * max(abs(left), abs(right)),
                 f'直行左右轮累计量不一致：left={left:.3f}, right={right:.3f}')
        encoder_distance = WHEEL_RADIUS * (left + right) / 2.0
        _require(abs(encoder_distance - odom_distance) <= 0.03,
                 f'直行累计量与里程计不一致：encoder={encoder_distance:.3f} m, '
                 f'odom={odom_distance:.3f} m')

        left_turn, right_turn, _, odom_yaw = _deltas(
            node.drive(angular=0.8))
        _require(left_turn < -0.5 and right_turn > 0.5,
                 f'左转累计方向错误：left={left_turn:.3f}, right={right_turn:.3f}')
        encoder_yaw = WHEEL_RADIUS * (right_turn - left_turn) / WHEEL_SEPARATION
        _require(odom_yaw > 0.2,
                 f'左转里程计方向错误：yaw={odom_yaw:.3f} rad')
        _require(abs(encoder_yaw - odom_yaw) <= 0.08,
                 f'转向累计量与里程计不一致：encoder={encoder_yaw:.3f} rad, '
                 f'odom={odom_yaw:.3f} rad')

        _require(all(math.isfinite(value) for sample in node.joints
                     for value in sample[1:3]), '编码器累计位置包含非有限值')
        print('M3仿真编码器复核通过')
        print(f'- 更新频率：{rate:.3f} Hz')
        print(f'- 直行轮累计量：left={left:.3f}, right={right:.3f} rad')
        print(f'- 直行距离：encoder={encoder_distance:.3f}, odom={odom_distance:.3f} m')
        print(f'- 左转轮累计量：left={left_turn:.3f}, right={right_turn:.3f} rad')
        print(f'- 左转角度：encoder={encoder_yaw:.3f}, odom={odom_yaw:.3f} rad')
        return 0
    except RuntimeError as error:
        print(f'M3仿真编码器复核失败：{error}')
        return 1
    finally:
        node.publisher.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
