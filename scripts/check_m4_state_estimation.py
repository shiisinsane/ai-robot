#!/usr/bin/env python3
"""验证M4-W4静止、直行、转向、融合里程计和唯一TF数据链。"""

import math
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu
from tf2_msgs.msg import TFMessage


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


class StateEstimationCheck(Node):
    def __init__(self):
        super().__init__('m4_state_estimation_check')
        self.raw = []
        self.fused = []
        self.imu = []
        self.odom_tf = []
        self.publisher = self.create_publisher(Twist, '/robot/safety_cmd_vel', 10)
        self.create_subscription(
            Odometry, '/robot/internal/base_odom', self.raw.append, 10)
        self.create_subscription(Odometry, '/robot/odom', self.fused.append, 10)
        imu_qos = QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.create_subscription(Imu, '/robot/imu/data', self.imu.append, imu_qos)
        self.create_subscription(TFMessage, '/tf', self._on_tf, 100)

    def _on_tf(self, message):
        for transform in message.transforms:
            if (transform.header.frame_id == 'odom' and
                    transform.child_frame_id == 'base_link'):
                self.odom_tf.append(transform)

    def wait_ready(self):
        deadline = time.monotonic() + 30.0
        while (len(self.raw) < 10 or len(self.fused) < 10 or
               len(self.imu) < 10 or len(self.odom_tf) < 5):
            _require(time.monotonic() < deadline, '等待EKF输入、输出或TF超时')
            rclpy.spin_once(self, timeout_sec=0.1)

    def drive(self, linear=0.0, angular=0.0, duration=1.2):
        start_raw = self.raw[-1]
        start_fused = self.fused[-1]
        command = Twist()
        command.linear.x = linear
        command.angular.z = angular
        start_stamp = start_fused.header.stamp.sec + start_fused.header.stamp.nanosec * 1e-9
        deadline = time.monotonic() + 20.0
        while True:
            now = self.fused[-1].header.stamp
            elapsed = now.sec + now.nanosec * 1e-9 - start_stamp
            if elapsed >= duration:
                break
            _require(time.monotonic() < deadline, '运动场景中仿真时间停止推进')
            self.publisher.publish(command)
            rclpy.spin_once(self, timeout_sec=0.02)
        self.publisher.publish(Twist())
        for _ in range(20):
            rclpy.spin_once(self, timeout_sec=0.02)
        return start_raw, self.raw[-1], start_fused, self.fused[-1]


def _pose_delta(start, end):
    dx = end.pose.pose.position.x - start.pose.pose.position.x
    dy = end.pose.pose.position.y - start.pose.pose.position.y
    dyaw = _angle_delta(_yaw(end.pose.pose.orientation),
                        _yaw(start.pose.pose.orientation))
    return dx, dy, dyaw


def _body_delta(start, end):
    dx, dy, dyaw = _pose_delta(start, end)
    start_yaw = _yaw(start.pose.pose.orientation)
    forward = math.cos(start_yaw) * dx + math.sin(start_yaw) * dy
    lateral = -math.sin(start_yaw) * dx + math.cos(start_yaw) * dy
    return forward, lateral, dyaw


def main():
    rclpy.init()
    node = StateEstimationCheck()
    try:
        node.wait_ready()
        static_start = node.fused[-1]
        static_time = time.monotonic() + 1.0
        while time.monotonic() < static_time:
            rclpy.spin_once(node, timeout_sec=0.05)
        static_dx, static_dy, static_yaw = _pose_delta(static_start, node.fused[-1])
        _require(math.hypot(static_dx, static_dy) < 0.03,
                 '静止位置漂移超过0.03 m')
        _require(abs(static_yaw) < 0.03, '静止航向漂移超过0.03 rad')

        straight = node.drive(linear=0.25, duration=1.5)
        raw_forward, _, raw_yaw = _body_delta(straight[0], straight[1])
        fused_forward, fused_lateral, fused_yaw = _body_delta(straight[2], straight[3])
        _require(fused_forward > 0.20,
                 f'融合里程计直行方向或距离错误：{fused_forward:.3f} m')
        _require(abs(fused_lateral) < 0.08 and abs(fused_yaw) < 0.10,
                 '融合里程计直行横向或航向偏差过大')
        _require(abs(fused_forward - raw_forward) < 0.08,
                 '融合与原始里程计直行距离差异过大')

        turn = node.drive(angular=0.8, duration=1.2)
        _, _, raw_turn = _pose_delta(turn[0], turn[1])
        _, _, fused_turn = _pose_delta(turn[2], turn[3])
        _require(fused_turn > 0.35, f'融合里程计左转方向或角度错误：{fused_turn:.3f} rad')
        _require(raw_turn > 0.35 and abs(fused_turn - raw_turn) < 0.15,
                 '融合与原始里程计转角不一致')

        final = node.fused[-1]
        values = [final.pose.pose.position.x, final.pose.pose.position.y,
                  _yaw(final.pose.pose.orientation), final.twist.twist.linear.x,
                  final.twist.twist.angular.z, *final.pose.covariance,
                  *final.twist.covariance]
        _require(all(math.isfinite(value) for value in values),
                 '融合里程计包含非有限值')
        _require(final.pose.covariance[0] > 0 and
                 final.pose.covariance[7] > 0 and
                 final.pose.covariance[35] > 0,
                 '融合位姿协方差未正确传播')

        transform = node.odom_tf[-1].transform
        _require(abs(transform.translation.x - final.pose.pose.position.x) < 0.05 and
                 abs(transform.translation.y - final.pose.pose.position.y) < 0.05,
                 'odom到base_link TF与融合里程计不一致')

        print('M4-W4编码器与IMU状态估计验证通过')
        print(f'- 静止漂移：position={math.hypot(static_dx, static_dy):.4f} m, '
              f'yaw={static_yaw:.4f} rad')
        print(f'- 直行：raw={raw_forward:.3f} m, fused={fused_forward:.3f} m, '
              f'lateral={fused_lateral:.3f} m')
        print(f'- 左转：raw={raw_turn:.3f} rad, fused={fused_turn:.3f} rad')
        print(f'- odom到base_link TF样本：{len(node.odom_tf)}')
        return 0
    except RuntimeError as error:
        print(f'M4-W4编码器与IMU状态估计验证失败：{error}')
        return 1
    finally:
        node.publisher.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
