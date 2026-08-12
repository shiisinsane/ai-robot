#!/usr/bin/env python3
"""执行M5-W9五次往返导航并核对成功率、终点精度和耗时。"""

import argparse
import math
import time

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import Twist
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener


def yaw_of(quaternion):
    return math.atan2(
        2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1.0 - 2.0 * (quaternion.y * quaternion.y + quaternion.z * quaternion.z))


def angle_error(left, right):
    return math.atan2(math.sin(left - right), math.cos(left - right))


class RepeatedNavigationCheck(Node):
    def __init__(self):
        super().__init__('m5_w9_repeated_navigation_check')
        self.client = ActionClient(
            self, NavigateToPose, '/robot/navigation/navigate_to_pose')
        self.zero = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.clear = self.create_client(Trigger, '/robot/safety/clear_faults')
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)

    def prepare(self):
        if not self.client.wait_for_server(timeout_sec=30.0):
            raise RuntimeError('公共导航Action不可用')
        if not self.clear.wait_for_service(timeout_sec=5.0):
            raise RuntimeError('安全清除Service不可用')
        for _ in range(3):
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                self.zero.publish(Twist())
                rclpy.spin_once(self, timeout_sec=0.05)
            future = self.clear.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
            if (future.done() and future.result() is not None and
                    future.result().success):
                return
        raise RuntimeError('安全故障清除失败')

    def run_goal(self, x, y, yaw, timeout):
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
        started = time.monotonic()
        sent = self.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, sent, timeout_sec=5.0)
        if not sent.done() or sent.result() is None or not sent.result().accepted:
            return False, time.monotonic() - started, math.inf, math.inf, '目标未接受'
        result = sent.result().get_result_async()
        rclpy.spin_until_future_complete(self, result, timeout_sec=timeout)
        elapsed = time.monotonic() - started
        if not result.done() or result.result() is None:
            return False, elapsed, math.inf, math.inf, '导航结果超时'
        status = result.result().status
        for _ in range(5):
            rclpy.spin_once(self, timeout_sec=0.1)
        try:
            transform = self.buffer.lookup_transform(
                'map', 'base_link', rclpy.time.Time())
            position = math.hypot(
                transform.transform.translation.x - x,
                transform.transform.translation.y - y)
            heading = abs(angle_error(
                yaw_of(transform.transform.rotation), yaw))
        except Exception as error:
            return False, elapsed, math.inf, math.inf, f'终点TF不可用：{error}'
        return (status == GoalStatus.STATUS_SUCCEEDED, elapsed, position,
                heading, f'Action状态{status}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--goal-a-x', type=float, default=0.8)
    parser.add_argument('--goal-a-y', type=float, default=0.0)
    parser.add_argument('--goal-a-yaw', type=float, default=0.0)
    parser.add_argument('--goal-b-x', type=float, default=0.0)
    parser.add_argument('--goal-b-y', type=float, default=0.0)
    parser.add_argument('--goal-b-yaw', type=float, default=0.0)
    parser.add_argument('--count', type=int, default=5)
    parser.add_argument('--timeout', type=float, default=90.0)
    parser.add_argument('--position-tolerance', type=float, default=0.15)
    parser.add_argument('--yaw-tolerance', type=float, default=0.15)
    args = parser.parse_args()
    if args.count < 5:
        print('M5-W9重复导航检查失败：正式检查次数不得少于5次')
        return 1
    rclpy.init()
    node = RepeatedNavigationCheck()
    try:
        node.prepare()
        goals = [(args.goal_a_x, args.goal_a_y, args.goal_a_yaw),
                 (args.goal_b_x, args.goal_b_y, args.goal_b_yaw)]
        records = []
        for index in range(args.count):
            target = goals[index % 2]
            record = node.run_goal(*target, args.timeout)
            records.append(record)
            print(f'- 第{index + 1}次：成功={record[0]}，耗时={record[1]:.3f} s，'
                  f'位置误差={record[2]:.3f} m，角度误差={record[3]:.3f} rad，{record[4]}')
            if not record[0]:
                break
        failures = []
        if len(records) != args.count or not all(item[0] for item in records):
            failures.append(f'成功次数{sum(item[0] for item in records)}/{args.count}')
        if any(item[2] > args.position_tolerance for item in records):
            failures.append('存在位置误差超限')
        if any(item[3] > args.yaw_tolerance for item in records):
            failures.append('存在角度误差超限')
        if failures:
            print('M5-W9重复导航检查失败：' + '；'.join(failures))
            return 1
        print(f'M5-W9重复导航检查通过：{args.count}/{args.count}成功')
        return 0
    except RuntimeError as error:
        print(f'M5-W9重复导航检查失败：{error}')
        return 1
    finally:
        node.zero.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
