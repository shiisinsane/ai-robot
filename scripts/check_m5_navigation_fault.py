#!/usr/bin/env python3
"""向运行中的M5导航注入输入断流，验证Action失败关闭和受控停车。"""

import argparse
import math
import os
import signal
import time

import psutil
import rclpy
from action_msgs.msg import GoalStatus
from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import Twist
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import Bool
from std_srvs.srv import Trigger


PROCESS_TOKEN = {
    'scan': 'scan_adapter.py',
    'odom': 'ekf_node',
    'imu': 'imu_adapter.py',
    'localization': 'nav2_amcl/amcl',
}
FAULT_CODE = {
    'scan': 'scan_timeout', 'odom': 'odom_timeout', 'imu': 'imu_timeout'}


def find_process(token):
    matches = []
    own = os.getpid()
    for process in psutil.process_iter(['pid', 'cmdline']):
        try:
            command = ' '.join(process.info['cmdline'] or [])
            if process.info['pid'] != own and token in command:
                matches.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if len(matches) != 1:
        raise RuntimeError(f'故障源进程匹配数应为1，实际{len(matches)}：{token}')
    return matches[0]


class NavigationFaultCheck(Node):
    def __init__(self):
        super().__init__('m5_w9_navigation_fault_check')
        self.client = ActionClient(
            self, NavigateToPose, '/robot/navigation/navigate_to_pose')
        self.commands = []
        self.stop = []
        self.codes = []
        self.zero = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.clear = self.create_client(Trigger, '/robot/safety/clear_faults')
        self.create_subscription(
            Twist, '/robot/safety_cmd_vel',
            lambda msg: self.commands.append(
                (time.monotonic(), msg.linear.x, msg.angular.z)), 50)
        self.create_subscription(
            Bool, '/robot/safety/stop_active',
            lambda msg: self.stop.append((time.monotonic(), msg.data)), 50)
        self.create_subscription(
            DiagnosticArray, '/robot/diagnostics', self._diagnostics, 50)

    def _diagnostics(self, message):
        for status in message.status:
            if status.name == 'safety_supervisor':
                values = {item.key: item.value for item in status.values}
                self.codes.append((time.monotonic(), values.get('code', '')))

    def spin_until(self, predicate, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not predicate():
            rclpy.spin_once(self, timeout_sec=0.04)
        return predicate()

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', choices=tuple(PROCESS_TOKEN))
    parser.add_argument('--goal-x', type=float, default=2.0)
    parser.add_argument('--goal-y', type=float, default=0.0)
    parser.add_argument('--goal-yaw', type=float, default=0.0)
    parser.add_argument('--motion-timeout', type=float, default=20.0)
    parser.add_argument('--failure-timeout', type=float, default=15.0)
    parser.add_argument('--maximum-stop-delay', type=float)
    args = parser.parse_args()
    if args.maximum_stop_delay is None:
        # AMCL会按0.5 s transform_tolerance发布未来TF；结合冻结的1.0 s
        # map->odom超时，定位断流从注入到停车允许2.0 s。停车级传感器仍为0.5 s。
        args.maximum_stop_delay = 2.0 if args.scenario == 'localization' else 0.5
    rclpy.init()
    node = NavigationFaultCheck()
    source = None
    try:
        node.prepare()
        source = find_process(PROCESS_TOKEN[args.scenario])
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.pose.position.x = args.goal_x
        goal.pose.pose.position.y = args.goal_y
        goal.pose.pose.orientation.z = math.sin(args.goal_yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(args.goal_yaw / 2.0)
        sent = node.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(node, sent, timeout_sec=5.0)
        if not sent.done() or sent.result() is None or not sent.result().accepted:
            raise RuntimeError('故障注入目标未接受')
        if not node.spin_until(
                lambda: any(abs(x) > 0.01 or abs(z) > 0.01
                            for _, x, z in node.commands), args.motion_timeout):
            raise RuntimeError('故障注入前未观察到运动')
        fault_at = time.monotonic()
        source.send_signal(signal.SIGSTOP)
        result = sent.result().get_result_async()
        rclpy.spin_until_future_complete(node, result, timeout_sec=args.failure_timeout)
        node.spin_until(lambda: False, 0.7)
        if not result.done() or result.result() is None:
            raise RuntimeError('输入断流后导航Action未在门限内结束')
        if result.result().status != GoalStatus.STATUS_ABORTED:
            raise RuntimeError(
                f'输入断流后Action状态应为ABORTED，实际{result.result().status}')
        moving_after = [stamp for stamp, x, z in node.commands
                        if stamp >= fault_at and
                        (abs(x) > 0.01 or abs(z) > 0.01)]
        stop_delay = max(moving_after) - fault_at if moving_after else 0.0
        if stop_delay > args.maximum_stop_delay:
            raise RuntimeError(f'故障到停车{stop_delay:.3f} s超过门限')
        expected = FAULT_CODE.get(args.scenario)
        if expected:
            if not any(expected in code for stamp, code in node.codes
                       if stamp >= fault_at):
                raise RuntimeError(f'安全诊断未报告{expected}')
            if not any(active for stamp, active in node.stop if stamp >= fault_at):
                raise RuntimeError('停车级输入断流未激活安全停车')
        print(f'M5-W9 {args.scenario}故障检查通过')
        print(f'- 公共Action返回ABORTED，故障到停车{stop_delay:.3f} s')
        if expected:
            print(f'- 安全诊断锁存{expected}，安全停车已激活')
        else:
            print('- 定位TF超时触发导航失败关闭')
        return 0
    except RuntimeError as error:
        print(f'M5-W9故障检查失败：{error}')
        return 1
    finally:
        if source is not None:
            try:
                source.send_signal(signal.SIGCONT)
            except psutil.Error:
                pass
        node.zero.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
