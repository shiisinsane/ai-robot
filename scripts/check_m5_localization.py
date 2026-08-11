#!/usr/bin/env python3
"""量化AMCL初始偏差收敛、运动稳定性、TF权威和异常输入处理。"""

import argparse
import math
import statistics
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener


def yaw_from_quaternion(quaternion):
    """返回平面四元数的yaw。"""
    return math.atan2(
        2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1.0 - 2.0 * (quaternion.y * quaternion.y + quaternion.z * quaternion.z),
    )


def angle_error(left, right):
    """返回[-pi, pi]内的角度差。"""
    return math.atan2(math.sin(left - right), math.cos(left - right))


def relative_pose_error(amcl_start, amcl_end, odom_start, odom_end):
    """比较AMCL和里程计在同一段运动中的相对位姿增量。"""
    amcl_distance = math.hypot(amcl_end[0] - amcl_start[0],
                               amcl_end[1] - amcl_start[1])
    odom_distance = math.hypot(odom_end[0] - odom_start[0],
                               odom_end[1] - odom_start[1])
    return (abs(amcl_distance - odom_distance),
            abs(angle_error(amcl_end[2] - amcl_start[2],
                            odom_end[2] - odom_start[2])))


class Check(Node):
    def __init__(self):
        super().__init__('m5_localization_check')
        self.poses = []
        self.odom = []
        self.tf_samples = []
        self.initialpose = self.create_publisher(
            PoseWithCovarianceStamped, '/robot/initialpose', 10)
        self.command = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.clear_client = self.create_client(Trigger, '/robot/safety/clear_faults')
        self.create_subscription(PoseWithCovarianceStamped, '/robot/pose',
                                 self._pose_callback, 10)
        self.create_subscription(Odometry, '/robot/odom', self._odom_callback, 10)
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)

    def _pose_callback(self, message):
        pose = message.pose.pose
        self.poses.append((pose.position.x, pose.position.y,
                           yaw_from_quaternion(pose.orientation), time.monotonic()))

    def _odom_callback(self, message):
        pose = message.pose.pose
        self.odom.append((pose.position.x, pose.position.y,
                          yaw_from_quaternion(pose.orientation), time.monotonic()))

    def sample_for(self, duration):
        deadline = time.monotonic() + duration
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            try:
                transform = self.buffer.lookup_transform(
                    'map', 'base_link', rclpy.time.Time())
                self.tf_samples.append((transform.transform.translation.x,
                                        transform.transform.translation.y))
            except Exception:
                pass

    def publish_initial_pose(self, x, y, yaw, frame='map'):
        message = PoseWithCovarianceStamped()
        message.header.frame_id = frame
        # 零时间戳要求AMCL使用最新TF，避免加速仿真中的微小向未来外推。
        message.pose.pose.position.x = x
        message.pose.pose.position.y = y
        message.pose.pose.orientation.z = math.sin(yaw / 2.0)
        message.pose.pose.orientation.w = math.cos(yaw / 2.0)
        message.pose.covariance[0] = 0.09
        message.pose.covariance[7] = 0.09
        message.pose.covariance[35] = 0.04
        for _ in range(5):
            self.initialpose.publish(message)
            rclpy.spin_once(self, timeout_sec=0.1)

    def clear_faults(self):
        if not self.clear_client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError('安全故障清除Service不可用')
        # command_timeout也属于锁存条件；清除前持续零速，确保命令链新鲜。
        for _ in range(3):
            deadline = time.monotonic() + 0.8
            while time.monotonic() < deadline:
                self.command.publish(Twist())
                rclpy.spin_once(self, timeout_sec=0.08)
            future = self.clear_client.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
            if (future.done() and future.result() is not None and
                    future.result().success):
                return
        raise RuntimeError('安全故障清除失败')

    def drive(self, linear, angular, duration):
        message = Twist()
        message.linear.x = linear
        message.angular.z = angular
        deadline = time.monotonic() + duration
        while rclpy.ok() and time.monotonic() < deadline:
            self.command.publish(message)
            self.sample_for(0.08)
        self.stop()

    def stop(self):
        self.command.publish(Twist())
        self.sample_for(0.8)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settle-duration', type=float, default=8.0)
    parser.add_argument('--initial-x', type=float, default=0.20)
    parser.add_argument('--initial-y', type=float, default=-0.10)
    parser.add_argument('--initial-yaw', type=float, default=0.10)
    parser.add_argument('--position-tolerance', type=float, default=0.15)
    parser.add_argument('--yaw-tolerance', type=float, default=0.15)
    args = parser.parse_args()
    rclpy.init()
    node = Check()
    errors = []
    try:
        node.sample_for(2.0)
        node.publish_initial_pose(args.initial_x, args.initial_y, args.initial_yaw)
        node.clear_faults()
        # 轻微旋转和直行让粒子滤波获得足够的非对称雷达观测。
        node.drive(0.0, 0.30, 1.5)
        node.drive(0.18, 0.0, 2.0)
        node.sample_for(args.settle_duration)

        if len(node.poses) < 2 or len(node.odom) < 20:
            errors.append('AMCL位姿或里程计样本不足')
        if len(node.tf_samples) < 20:
            errors.append('定位TF样本不足')
            jitter = math.inf
        else:
            tail = node.tf_samples[-min(50, len(node.tf_samples)):]
            jitter = math.hypot(statistics.pstdev(item[0] for item in tail),
                                statistics.pstdev(item[1] for item in tail))
            if jitter > 0.03:
                errors.append(f'静止位置抖动{jitter:.4f} m超过0.03 m')

        if node.poses and node.odom:
            final_pose = node.poses[-1]
            final_odom = node.odom[-1]
            position_error = math.hypot(final_pose[0] - final_odom[0],
                                        final_pose[1] - final_odom[1])
            yaw_error = abs(angle_error(final_pose[2], final_odom[2]))
            if position_error > args.position_tolerance:
                errors.append(f'初始偏差收敛位置误差{position_error:.3f} m超限')
            if yaw_error > args.yaw_tolerance:
                errors.append(f'初始偏差收敛角度误差{yaw_error:.3f} rad超限')
        else:
            position_error = yaw_error = math.inf

        # 非map坐标系初始位姿应被AMCL拒绝，且不能破坏既有定位输出和TF。
        tf_before_invalid = node.tf_samples[-1] if node.tf_samples else None
        node.publish_initial_pose(5.0, 5.0, 1.0, frame='invalid_frame')
        node.sample_for(2.0)
        if not node.buffer.can_transform('map', 'odom', rclpy.time.Time()):
            errors.append('缺少AMCL发布的map到odom TF')
        if tf_before_invalid and node.tf_samples:
            invalid_jump = math.hypot(node.tf_samples[-1][0] - tf_before_invalid[0],
                                      node.tf_samples[-1][1] - tf_before_invalid[1])
            if invalid_jump > 0.05:
                errors.append(f'无效初始位姿导致定位TF跳变{invalid_jump:.3f} m')

        if errors:
            print('M5-W5定位检查失败：' + '；'.join(errors))
            return 1
        print('M5-W5定位检查通过')
        print(f'- 冻结初始偏差：({args.initial_x:.2f}, {args.initial_y:.2f}, '
              f'{args.initial_yaw:.2f} rad)')
        print(f'- 收敛误差：位置{position_error:.3f} m，角度{yaw_error:.3f} rad')
        print(f'- 样本：位姿{len(node.poses)}条、里程计{len(node.odom)}条、'
              f'TF {len(node.tf_samples)}条；静止抖动{jitter:.4f} m')
        print('- 非map初始位姿被拒绝后，既有定位输出和TF保持有效')
        return 0
    except (KeyboardInterrupt, RuntimeError) as error:
        print(f'M5-W5定位检查失败：{error}')
        return 1
    finally:
        node.stop()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
