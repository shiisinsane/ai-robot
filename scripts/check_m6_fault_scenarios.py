#!/usr/bin/env python3
"""验证M6-W7输入、导航、感知和安全故障的任务级传播。"""

import argparse
import math
import os
import signal
import time

from action_msgs.msg import GoalStatus, GoalStatusArray
from geometry_msgs.msg import Twist
import psutil
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from robot_interfaces.action import ExecuteRobotTask
from std_msgs.msg import Bool
from std_srvs.srv import Trigger


PROCESS_TOKEN = {
    'camera': 'camera_adapter.py',
    'scan': 'scan_adapter.py',
    'imu': 'imu_adapter.py',
    'odom': 'ekf_node',
    'localization': 'nav2_amcl/amcl',
}


def find_process(token):
    matches = []
    for process in psutil.process_iter(['pid', 'cmdline']):
        try:
            command = ' '.join(process.info['cmdline'] or [])
            if process.pid != os.getpid() and token in command:
                matches.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if len(matches) != 1:
        raise RuntimeError(f'故障进程匹配数应为1，实际{len(matches)}：{token}')
    return matches[0]


class FaultCheck(Node):
    def __init__(self):
        super().__init__('m6_w7_fault_check')
        self.client = ActionClient(self, ExecuteRobotTask, '/robot/task/execute')
        self.zero = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.zero_timer = None
        self.clear = self.create_client(Trigger, '/robot/safety/clear_faults')
        self.stop_active = True
        self.feedback = []
        self.nav_status = []
        self.safety_commands = []
        self.create_subscription(
            Bool, '/robot/safety/stop_active',
            lambda message: setattr(self, 'stop_active', message.data), 20)
        self.create_subscription(
            Twist, '/robot/safety_cmd_vel',
            lambda message: self.safety_commands.append(
                (time.monotonic(), message.linear.x, message.angular.z)), 50)
        self.create_subscription(
            GoalStatusArray, '/robot/navigation/navigate_to_pose/_action/status',
            lambda message: setattr(self, 'nav_status', message.status_list), 20)

    def _keepalive(self):
        if self.zero_timer is None or self.zero_timer.is_canceled():
            self.zero_timer = self.create_timer(
                0.05, lambda: self.zero.publish(Twist()))

    def _release_keepalive(self):
        if self.zero_timer is not None:
            self.zero_timer.cancel()

    @staticmethod
    def goal(task_id, x=0.0, y=0.0, frame='map'):
        goal = ExecuteRobotTask.Goal()
        goal.task_id = task_id
        goal.task_type = goal.TASK_NAVIGATE_AND_SENSE
        goal.target_pose.header.frame_id = frame
        goal.target_pose.pose.position.x = x
        goal.target_pose.pose.position.y = y
        goal.target_pose.pose.orientation.w = 1.0
        goal.sensing_mode = goal.SENSING_BASIC_SNAPSHOT
        goal.task_timeout_sec = 60.0
        return goal

    def prepare(self):
        self._keepalive()
        if not self.clear.wait_for_service(timeout_sec=10.0):
            raise RuntimeError('安全清除Service不可用')
        for _ in range(3):
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                self.zero.publish(Twist())
                rclpy.spin_once(self, timeout_sec=0.05)
            future = self.clear.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
            if future.done() and future.result() and future.result().success:
                deadline = time.monotonic() + 3.0
                while self.stop_active and time.monotonic() < deadline:
                    rclpy.spin_once(self, timeout_sec=0.05)
                if not self.stop_active:
                    return
        raise RuntimeError('安全故障清除失败')

    def send(self, goal, timeout=70.0, release_keepalive=False):
        self.feedback = []
        future = self.client.send_goal_async(
            goal, feedback_callback=lambda message: self.feedback.append(
                message.feedback.phase))
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        if not future.done() or future.result() is None or not future.result().accepted:
            raise RuntimeError('任务目标未接受')
        if release_keepalive:
            self._release_keepalive()
        result = future.result().get_result_async()
        rclpy.spin_until_future_complete(self, result, timeout_sec=timeout)
        if not result.done() or result.result() is None:
            raise RuntimeError('任务结果超时')
        return result.result()

    def wait_motion(self, timeout=20.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.04)
            if any(abs(x) > 0.01 or abs(z) > 0.01
                   for _, x, z in self.safety_commands):
                return
        raise RuntimeError('故障注入前未观察到运动')

    def no_active_navigation(self):
        deadline = time.monotonic() + 0.7
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
        return not any(item.status in (
            GoalStatus.STATUS_ACCEPTED, GoalStatus.STATUS_EXECUTING,
            GoalStatus.STATUS_CANCELING) for item in self.nav_status)


def run_input(node):
    cases = (
        ('outside', node.goal('w7-outside', 20.0, 20.0)),
        ('frame', node.goal('w7-frame', frame='odom')),
        ('nonfinite', node.goal('w7-nonfinite', x=math.nan)),
    )
    for name, goal in cases:
        before = len(node.safety_commands)
        wrapped = node.send(goal, 5.0)
        if (wrapped.status != GoalStatus.STATUS_ABORTED or
                wrapped.result.error_code !=
                ExecuteRobotTask.Result.ERROR_INVALID_TARGET):
            raise RuntimeError(f'{name}目标未返回输入错误')
        if ExecuteRobotTask.Feedback.PHASE_NAVIGATING in node.feedback:
            raise RuntimeError(f'{name}目标进入了导航阶段')
        moving = node.safety_commands[before:]
        if any(abs(x) > 0.01 or abs(z) > 0.01 for _, x, z in moving):
            raise RuntimeError(f'{name}目标拒绝期间产生运动命令')
    print('M6-W7输入故障检查通过：3/3运动前拒绝')


def run_unreachable(node):
    wrapped = node.send(node.goal('w7-unreachable', 1.7, 1.4))
    if (wrapped.status != GoalStatus.STATUS_ABORTED or
            wrapped.result.error_code !=
            ExecuteRobotTask.Result.ERROR_NAVIGATION_FAILED):
        raise RuntimeError(
            f'障碍内目标结果异常：{wrapped.status}/{wrapped.result.error_code}')
    if not node.no_active_navigation():
        raise RuntimeError('不可达任务结束后仍有活动导航目标')
    print('M6-W7不可达故障检查通过：ERROR_NAVIGATION_FAILED且下游已结束')


def run_stream_fault(node, scenario):
    source = find_process(PROCESS_TOKEN[scenario])
    try:
        goal_x = 0.8 if scenario == 'camera' else 2.0
        sent = node.client.send_goal_async(
            node.goal(f'w7-{scenario}', goal_x, 0.0),
            feedback_callback=lambda message: node.feedback.append(
                message.feedback.phase))
        rclpy.spin_until_future_complete(node, sent, timeout_sec=5.0)
        if not sent.done() or not sent.result() or not sent.result().accepted:
            raise RuntimeError('故障任务未接受')
        node.wait_motion()
        node._release_keepalive()
        fault_at = time.monotonic()
        source.send_signal(signal.SIGSTOP)
        result = sent.result().get_result_async()
        rclpy.spin_until_future_complete(node, result, timeout_sec=30.0)
        if not result.done() or not result.result():
            raise RuntimeError('断流后任务未结束')
        wrapped = result.result()
        expected = {
            'camera': ExecuteRobotTask.Result.ERROR_SENSOR_STALE,
            'localization': ExecuteRobotTask.Result.ERROR_NAVIGATION_FAILED,
        }.get(scenario, ExecuteRobotTask.Result.ERROR_SAFETY_STOP)
        if wrapped.status != GoalStatus.STATUS_ABORTED or wrapped.result.error_code != expected:
            raise RuntimeError(
                f'{scenario}断流结果异常：{wrapped.status}/{wrapped.result.error_code}')
        if scenario in ('scan', 'imu', 'odom') and not node.stop_active:
            raise RuntimeError(f'{scenario}断流未激活安全停车')
        if not node.no_active_navigation():
            raise RuntimeError(f'{scenario}断流后仍有活动导航目标')
        moving_after = [stamp for stamp, x, z in node.safety_commands
                        if stamp >= fault_at and
                        (abs(x) > 0.01 or abs(z) > 0.01)]
        stop_delay = max(moving_after) - fault_at if moving_after else 0.0
        if scenario == 'camera':
            print('M6-W7 camera断流检查通过：ERROR_SENSOR_STALE，未升级为安全停车')
        elif scenario == 'localization':
            print('M6-W7 localization断流检查通过：ERROR_NAVIGATION_FAILED且下游已结束')
        else:
            print(f'M6-W7 {scenario}断流检查通过：ERROR_SAFETY_STOP，'
                  f'故障到最后非零安全命令{stop_delay:.3f} s')
    finally:
        try:
            source.send_signal(signal.SIGCONT)
        except psutil.Error:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', choices=('input', 'unreachable', *PROCESS_TOKEN))
    args = parser.parse_args()
    rclpy.init()
    node = FaultCheck()
    try:
        if not node.client.wait_for_server(timeout_sec=30.0):
            raise RuntimeError('公共任务Action不可用')
        node.prepare()
        if args.scenario == 'input':
            run_input(node)
        elif args.scenario == 'unreachable':
            run_unreachable(node)
        else:
            run_stream_fault(node, args.scenario)
        return 0
    except (RuntimeError, Exception) as error:
        print(f'M6-W7故障检查失败：{error}')
        return 1
    finally:
        node.zero.publish(Twist())
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
