#!/usr/bin/env python3
"""黑盒检查M6-W3任务服务端的校验、受控空实现、取消和诊断。"""

import time

from action_msgs.msg import GoalStatus
from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import Twist
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from robot_interfaces.action import ExecuteRobotTask


class SkeletonCheck(Node):
    def __init__(self):
        super().__init__('m6_w3_skeleton_check')
        self.client = ActionClient(self, ExecuteRobotTask, '/robot/task/execute')
        self.diagnostics = []
        self.velocity_messages = []
        self.create_subscription(
            DiagnosticArray, '/robot/diagnostics', self._diagnostic, 20)
        self.create_subscription(
            Twist, '/robot/cmd_vel', self.velocity_messages.append, 20)

    def _diagnostic(self, message):
        self.diagnostics.extend(
            status for status in message.status if status.name == 'task_manager')

    @staticmethod
    def goal(task_id='w3-valid', frame='map'):
        goal = ExecuteRobotTask.Goal()
        goal.task_id = task_id
        goal.task_type = goal.TASK_NAVIGATE_AND_SENSE
        goal.target_pose.header.frame_id = frame
        goal.target_pose.pose.orientation.w = 1.0
        goal.sensing_mode = goal.SENSING_BASIC_SNAPSHOT
        goal.task_timeout_sec = 60.0
        return goal

    def send(self, task_id='w3-valid', frame='map'):
        goal = self.goal(task_id, frame)
        sent = self.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, sent, timeout_sec=5.0)
        if not sent.done() or sent.result() is None or not sent.result().accepted:
            raise RuntimeError('任务目标未被服务端接受')
        result = sent.result().get_result_async()
        rclpy.spin_until_future_complete(self, result, timeout_sec=5.0)
        if not result.done() or result.result() is None:
            raise RuntimeError('任务结果超时')
        return result.result()


def main():
    rclpy.init()
    node = SkeletonCheck()
    try:
        if not node.client.wait_for_server(timeout_sec=10.0):
            raise RuntimeError('公共任务Action不可用')
        invalid = node.send(task_id='bad id')
        if (invalid.status != GoalStatus.STATUS_ABORTED or
                invalid.result.error_code !=
                ExecuteRobotTask.Result.ERROR_INVALID_TASK_ID):
            raise RuntimeError('非法task_id未返回预期ABORTED和错误码')
        valid = node.send()
        if (valid.status != GoalStatus.STATUS_ABORTED or
                valid.result.error_code !=
                ExecuteRobotTask.Result.ERROR_NAVIGATION_UNAVAILABLE):
            raise RuntimeError('W3合法任务未受控返回导航未接入')
        first = node.client.send_goal_async(node.goal('w3-active'))
        rclpy.spin_until_future_complete(node, first, timeout_sec=2.0)
        if not first.done() or not first.result().accepted:
            raise RuntimeError('并发检查的首个任务未接受')
        second = node.client.send_goal_async(node.goal('w3-concurrent'))
        rclpy.spin_until_future_complete(node, second, timeout_sec=2.0)
        if not second.done() or second.result() is None or second.result().accepted:
            raise RuntimeError('活动任务期间的第二个任务未被拒绝')
        cancel = first.result().cancel_goal_async()
        rclpy.spin_until_future_complete(node, cancel, timeout_sec=2.0)
        terminal = first.result().get_result_async()
        rclpy.spin_until_future_complete(node, terminal, timeout_sec=2.0)
        if (not terminal.done() or terminal.result().status !=
                GoalStatus.STATUS_CANCELED):
            raise RuntimeError('任务取消未进入CANCELED终态')
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not node.diagnostics:
            rclpy.spin_once(node, timeout_sec=0.1)
        if not node.diagnostics:
            raise RuntimeError('未收到task_manager诊断')
        if node.velocity_messages:
            raise RuntimeError('任务管理器骨架不应发布cmd_vel')
        print('M6-W3任务管理器骨架检查通过')
        print('- 非法目标返回ABORTED/ERROR_INVALID_TASK_ID')
        print('- 合法目标返回ABORTED/ERROR_NAVIGATION_UNAVAILABLE')
        print('- 单活动任务拒绝并发目标，取消进入CANCELED终态')
        print('- 诊断可见，未发布速度命令')
        return 0
    except RuntimeError as error:
        print(f'M6-W3任务管理器骨架检查失败：{error}')
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
