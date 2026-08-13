#!/usr/bin/env python3
"""验证M6-W6取消传播、总超时、并发拒绝和重复目标。"""

import argparse
import time

from action_msgs.msg import GoalStatus, GoalStatusArray
from geometry_msgs.msg import Twist
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from robot_interfaces.action import ExecuteRobotTask
from std_msgs.msg import Bool
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener


class ControlSemanticsCheck(Node):
    def __init__(self):
        super().__init__('m6_w6_control_semantics_check')
        self.client = ActionClient(self, ExecuteRobotTask, '/robot/task/execute')
        self.zero = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.zero_timer = None
        self.stop_active = True
        self.clear = self.create_client(Trigger, '/robot/safety/clear_faults')
        self.feedback = []
        self.navigation_status = []
        self.create_subscription(
            Bool, '/robot/safety/stop_active',
            lambda message: setattr(self, 'stop_active', message.data), 20)
        self.create_subscription(
            GoalStatusArray,
            '/robot/navigation/navigate_to_pose/_action/status',
            lambda message: setattr(self, 'navigation_status', message.status_list),
            20)
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)

    def _keepalive(self):
        if self.zero_timer is None or self.zero_timer.is_canceled():
            self.zero_timer = self.create_timer(
                0.05, lambda: self.zero.publish(Twist()))

    def _release_keepalive(self):
        if self.zero_timer is not None:
            self.zero_timer.cancel()

    def prepare(self):
        self._keepalive()
        if not self.clear.wait_for_service(timeout_sec=10.0):
            raise RuntimeError('安全故障清除Service不可用')
        for _ in range(3):
            for _ in range(20):
                rclpy.spin_once(self, timeout_sec=0.05)
            future = self.clear.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
            if (future.done() and future.result() is not None and
                    future.result().success):
                deadline = time.monotonic() + 3.0
                while self.stop_active and time.monotonic() < deadline:
                    rclpy.spin_once(self, timeout_sec=0.05)
                if not self.stop_active:
                    return
        raise RuntimeError('安全故障清除失败')

    @staticmethod
    def goal(task_id, x, y, timeout):
        goal = ExecuteRobotTask.Goal()
        goal.task_id = task_id
        goal.task_type = goal.TASK_NAVIGATE_AND_SENSE
        goal.target_pose.header.frame_id = 'map'
        goal.target_pose.pose.position.x = x
        goal.target_pose.pose.position.y = y
        goal.target_pose.pose.orientation.w = 1.0
        goal.sensing_mode = goal.SENSING_BASIC_SNAPSHOT
        goal.task_timeout_sec = timeout
        return goal

    def send(self, goal):
        self.feedback = []
        sent = self.client.send_goal_async(
            goal, feedback_callback=lambda message: self.feedback.append(
                message.feedback.phase))
        rclpy.spin_until_future_complete(self, sent, timeout_sec=5.0)
        if not sent.done() or sent.result() is None:
            raise RuntimeError('发送任务目标超时')
        return sent.result()

    def result(self, handle, timeout):
        future = handle.get_result_async()
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        if not future.done() or future.result() is None:
            raise RuntimeError('等待任务结果超时')
        return future.result()

    def wait_navigation_phase(self, timeout=10.0):
        deadline = time.monotonic() + timeout
        while (ExecuteRobotTask.Feedback.PHASE_NAVIGATING not in self.feedback and
               time.monotonic() < deadline):
            rclpy.spin_once(self, timeout_sec=0.05)
        if ExecuteRobotTask.Feedback.PHASE_NAVIGATING not in self.feedback:
            raise RuntimeError('任务未进入导航阶段')

    def verify_no_active_navigation(self):
        deadline = time.monotonic() + 0.6
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
        active = [item.status for item in self.navigation_status
                  if item.status in (GoalStatus.STATUS_ACCEPTED,
                                     GoalStatus.STATUS_EXECUTING,
                                     GoalStatus.STATUS_CANCELING)]
        if active:
            raise RuntimeError(f'任务终态后仍有活动导航状态：{active}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cancel-goal-x', type=float, default=1.5)
    parser.add_argument('--timeout-goal-x', type=float, default=2.2)
    parser.add_argument('--task-timeout', type=float, default=10.0)
    args = parser.parse_args()
    rclpy.init()
    node = ControlSemanticsCheck()
    try:
        if not node.client.wait_for_server(timeout_sec=30.0):
            raise RuntimeError('公共任务Action不可用')
        node.prepare()

        first = node.send(node.goal('m6-w6-cancel', args.cancel_goal_x, 0.0, 60.0))
        if not first.accepted:
            raise RuntimeError('取消场景首个任务未接受')
        node._release_keepalive()
        node.wait_navigation_phase()
        second = node.send(node.goal('m6-w6-concurrent', 0.2, 0.0, 60.0))
        if second.accepted:
            raise RuntimeError('活动任务期间第二个目标未被拒绝')
        cancel_started = time.monotonic()
        canceled = first.cancel_goal_async()
        rclpy.spin_until_future_complete(node, canceled, timeout_sec=2.0)
        terminal = node.result(first, 4.0)
        cancel_elapsed = time.monotonic() - cancel_started
        if (terminal.status != GoalStatus.STATUS_CANCELED or
                terminal.result.error_code !=
                ExecuteRobotTask.Result.ERROR_NAVIGATION_CANCELED):
            raise RuntimeError('用户取消未返回CANCELED和稳定错误码')
        if cancel_elapsed > 2.5:
            raise RuntimeError(f'取消传播耗时{cancel_elapsed:.3f} s超限')
        node.verify_no_active_navigation()

        node.prepare()
        timeout_handle = node.send(node.goal(
            'm6-w6-timeout', args.timeout_goal_x, 0.0, args.task_timeout))
        if not timeout_handle.accepted:
            raise RuntimeError('超时场景任务未接受')
        node._release_keepalive()
        timeout_started = time.monotonic()
        timed_out = node.result(timeout_handle, args.task_timeout + 5.0)
        timeout_elapsed = time.monotonic() - timeout_started
        if (timed_out.status != GoalStatus.STATUS_ABORTED or
                timed_out.result.error_code !=
                ExecuteRobotTask.Result.ERROR_TASK_TIMEOUT):
            raise RuntimeError(
                f'端到端超时结果异常：{timed_out.status}/'
                f'{timed_out.result.error_code}')
        if not args.task_timeout - 0.5 <= timeout_elapsed <= args.task_timeout + 2.5:
            raise RuntimeError(f'端到端超时耗时{timeout_elapsed:.3f} s异常')
        node.verify_no_active_navigation()

        node.prepare()
        transform = node.buffer.lookup_transform(
            'map', 'base_link', rclpy.time.Time())
        repeat_x = transform.transform.translation.x
        repeat_y = transform.transform.translation.y
        repeated = []
        for index in range(2):
            handle = node.send(node.goal(
                f'm6-w6-repeat-{index}', repeat_x, repeat_y, 60.0))
            if not handle.accepted:
                raise RuntimeError(f'重复目标第{index + 1}次未接受')
            node._release_keepalive()
            result = node.result(handle, 60.0)
            if (result.status != GoalStatus.STATUS_SUCCEEDED or
                    not result.result.success):
                raise RuntimeError(f'重复目标第{index + 1}次未成功')
            repeated.append(result.result.snapshot.scan_sample_count)
            node._keepalive()
        if any(count == 0 for count in repeated):
            raise RuntimeError('重复目标快照不完整')

        print('M6-W6取消、超时与并发检查通过')
        print(f'- 并发目标明确拒绝，取消传播{cancel_elapsed:.3f} s且下游已结束')
        print(f'- 端到端超时{timeout_elapsed:.3f} s，返回ERROR_TASK_TIMEOUT')
        print(f'- 相同目标连续执行2/2成功，雷达点数{repeated}')
        return 0
    except (RuntimeError, Exception) as error:
        print(f'M6-W6取消、超时与并发检查失败：{error}')
        return 1
    finally:
        node.zero.publish(Twist())
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
