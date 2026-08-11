#!/usr/bin/env python3
"""验证W8公共导航Action的取消、失败状态和受控停车。"""

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


class RecoveryCheck(Node):
    def __init__(self):
        super().__init__('m5_recovery_check')
        self.client = ActionClient(
            self, NavigateToPose, '/robot/navigation/navigate_to_pose')
        self.commands = []
        self.feedback = []
        self.zero_command = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.clear_client = self.create_client(
            Trigger, '/robot/safety/clear_faults')
        self.create_subscription(Twist, '/robot/cmd_vel', self._command, 10)

    def _command(self, message):
        self.commands.append((time.monotonic(), message.linear.x,
                              message.angular.z))

    def prepare_safety(self):
        if not self.clear_client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError('安全清除Service不可用')
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            self.zero_command.publish(Twist())
            rclpy.spin_once(self, timeout_sec=0.08)
        future = self.clear_client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        if not future.done() or future.result() is None or not future.result().success:
            raise RuntimeError('安全故障清除失败')


def make_goal(x, y, yaw):
    goal = NavigateToPose.Goal()
    goal.pose.header.frame_id = 'map'
    goal.pose.pose.position.x = x
    goal.pose.pose.position.y = y
    goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
    goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
    return goal


def spin_until(node, predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not predicate():
        rclpy.spin_once(node, timeout_sec=0.05)
    return predicate()


def run_cancel(node, args):
    node.commands.clear()
    node.feedback.clear()
    send = node.client.send_goal_async(
        make_goal(args.goal_x, args.goal_y, args.goal_yaw),
        feedback_callback=lambda message: node.feedback.append(message.feedback))
    rclpy.spin_until_future_complete(node, send, timeout_sec=5.0)
    if not send.done() or send.result() is None or not send.result().accepted:
        return ['公共导航目标未接受']
    handle = send.result()
    if not spin_until(node, lambda: any(
            abs(x) > 0.01 or abs(z) > 0.01 for _, x, z in node.commands),
            args.motion_timeout):
        return ['取消前未观察到机器人运动']
    requested = time.monotonic()
    cancel = handle.cancel_goal_async()
    rclpy.spin_until_future_complete(node, cancel, timeout_sec=5.0)
    if (not cancel.done() or cancel.result() is None or
            not cancel.result().goals_canceling):
        return ['公共导航Action未接受取消']
    result = handle.get_result_async()
    rclpy.spin_until_future_complete(node, result, timeout_sec=5.0)
    if (not result.done() or result.result() is None or
            result.result().status != GoalStatus.STATUS_CANCELED):
        status = None if not result.done() or result.result() is None else result.result().status
        return [f'取消后的Action状态错误：{status}']
    spin_until(node, lambda: False, 0.7)
    moving_after = [stamp for stamp, x, z in node.commands
                    if stamp >= requested and
                    (abs(x) > 0.01 or abs(z) > 0.01)]
    stop_delay = (max(moving_after) - requested) if moving_after else 0.0
    if stop_delay > args.maximum_stop_delay:
        return [f'取消到停车{stop_delay:.3f} s超过门限']
    print('M5-W8取消检查通过')
    print(f'- Action状态为CANCELED，取消到停车{stop_delay:.3f} s')
    print(f'- 收到导航反馈{len(node.feedback)}条')
    return []


def run_failure(node, args):
    node.commands.clear()
    send = node.client.send_goal_async(make_goal(args.goal_x, args.goal_y, 0.0))
    rclpy.spin_until_future_complete(node, send, timeout_sec=5.0)
    if not send.done() or send.result() is None or not send.result().accepted:
        return ['公共不可达目标未被Action服务器接收']
    result = send.result().get_result_async()
    rclpy.spin_until_future_complete(node, result, timeout_sec=args.failure_timeout)
    if not result.done() or result.result() is None:
        return ['不可达目标未在门限内返回失败']
    if result.result().status != GoalStatus.STATUS_ABORTED:
        return [f'不可达目标Action状态错误：{result.result().status}']
    moving = [(x, z) for _, x, z in node.commands
              if abs(x) > 0.01 or abs(z) > 0.01]
    if moving:
        return ['不可达目标失败期间产生了运动命令']
    print('M5-W8失败反馈检查通过')
    print('- 不可达目标Action状态为ABORTED，且未产生运动命令')
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', choices=['cancel', 'failure'])
    parser.add_argument('--goal-x', type=float)
    parser.add_argument('--goal-y', type=float)
    parser.add_argument('--goal-yaw', type=float, default=0.0)
    parser.add_argument('--motion-timeout', type=float, default=15.0)
    parser.add_argument('--maximum-stop-delay', type=float, default=0.5)
    parser.add_argument('--failure-timeout', type=float, default=20.0)
    args = parser.parse_args()
    if args.goal_x is None:
        args.goal_x = 2.0 if args.scenario == 'cancel' else 8.0
    if args.goal_y is None:
        args.goal_y = 0.0
    rclpy.init()
    node = RecoveryCheck()
    try:
        if not node.client.wait_for_server(timeout_sec=30.0):
            print('M5-W8检查失败：公共导航Action不可用')
            return 1
        node.prepare_safety()
        errors = (run_cancel(node, args) if args.scenario == 'cancel'
                  else run_failure(node, args))
        if errors:
            print('M5-W8检查失败：' + '；'.join(errors))
            return 1
        return 0
    except RuntimeError as error:
        print(f'M5-W8检查失败：{error}')
        return 1
    finally:
        node.zero_command.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
