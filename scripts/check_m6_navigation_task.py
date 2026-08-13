#!/usr/bin/env python3
"""执行M6-W5端到端导航与到点感知，核对结构化结果。"""

import argparse
import math

from action_msgs.msg import GoalStatus
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from robot_interfaces.action import ExecuteRobotTask
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import Twist
from std_srvs.srv import Trigger
from std_msgs.msg import Bool
from tf2_ros import Buffer, TransformListener


class NavigationTaskCheck(Node):
    def __init__(self):
        super().__init__('m6_w4_navigation_task_check')
        self.client = ActionClient(self, ExecuteRobotTask, '/robot/task/execute')
        self.navigation = ActionClient(
            self, NavigateToPose, '/robot/navigation/navigate_to_pose')
        self.feedback = []
        self.zero = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.zero_timer = self.create_timer(0.05, lambda: self.zero.publish(Twist()))
        self.clear = self.create_client(Trigger, '/robot/safety/clear_faults')
        self.stop_active = True
        self.create_subscription(
            Bool, '/robot/safety/stop_active',
            lambda message: setattr(self, 'stop_active', message.data), 20)
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)

    def feedback_callback(self, message):
        item = message.feedback
        self.feedback.append((item.phase, item.progress, item.message))

    def prepare(self):
        if not self.clear.wait_for_service(timeout_sec=10.0):
            raise RuntimeError('安全故障清除Service不可用')
        for _ in range(3):
            for _ in range(20):
                self.zero.publish(Twist())
                rclpy.spin_once(self, timeout_sec=0.05)
            future = self.clear.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
            if (future.done() and future.result() is not None and
                    future.result().success):
                deadline = self.get_clock().now().nanoseconds + int(3e9)
                while (self.stop_active and
                       self.get_clock().now().nanoseconds < deadline):
                    rclpy.spin_once(self, timeout_sec=0.05)
                if not self.stop_active:
                    # 给任务管理器的独立订阅同样留出一次DDS交付窗口。
                    for _ in range(2):
                        rclpy.spin_once(self, timeout_sec=0.05)
                    return
        raise RuntimeError('安全故障清除失败')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--goal-x', type=float, default=0.8)
    parser.add_argument('--goal-y', type=float, default=0.0)
    parser.add_argument('--goal-yaw', type=float, default=0.0)
    parser.add_argument('--timeout', type=float, default=180.0)
    parser.add_argument('--position-tolerance', type=float, default=0.15)
    args = parser.parse_args()
    rclpy.init()
    node = NavigationTaskCheck()
    try:
        if not node.client.wait_for_server(timeout_sec=30.0):
            raise RuntimeError('公共任务Action不可用')
        if not node.navigation.wait_for_server(timeout_sec=45.0):
            raise RuntimeError('公共导航Action不可用')
        # 导航Action早于全部输入看门狗稳定可见，留出短暂稳态窗口。
        for _ in range(40):
            rclpy.spin_once(node, timeout_sec=0.05)
        node.prepare()
        goal = ExecuteRobotTask.Goal()
        goal.task_id = 'm6-w5-snapshot'
        goal.task_type = goal.TASK_NAVIGATE_AND_SENSE
        goal.target_pose.header.frame_id = 'map'
        goal.target_pose.pose.position.x = args.goal_x
        goal.target_pose.pose.position.y = args.goal_y
        goal.target_pose.pose.orientation.z = math.sin(args.goal_yaw / 2.0)
        goal.target_pose.pose.orientation.w = math.cos(args.goal_yaw / 2.0)
        goal.sensing_mode = goal.SENSING_BASIC_SNAPSHOT
        goal.task_timeout_sec = args.timeout
        sent = node.client.send_goal_async(
            goal, feedback_callback=node.feedback_callback)
        rclpy.spin_until_future_complete(node, sent, timeout_sec=5.0)
        if not sent.done() or sent.result() is None or not sent.result().accepted:
            raise RuntimeError('任务目标未接受')
        node.zero_timer.cancel()
        result = sent.result().get_result_async()
        rclpy.spin_until_future_complete(node, result, timeout_sec=args.timeout + 10.0)
        if not result.done() or result.result() is None:
            raise RuntimeError('任务结果超时')
        wrapped = result.result()
        if wrapped.status != GoalStatus.STATUS_SUCCEEDED:
            raise RuntimeError(
                f'W5终态应为SUCCEEDED，实际{wrapped.status}，错误码'
                f'{wrapped.result.error_code}：{wrapped.result.message}')
        if (not wrapped.result.success or wrapped.result.error_code !=
                ExecuteRobotTask.Result.ERROR_NONE):
            raise RuntimeError(
                f'W5任务结果异常：{wrapped.result.error_code} '
                f'{wrapped.result.message}')
        phases = [item[0] for item in node.feedback]
        required = [ExecuteRobotTask.Feedback.PHASE_ACCEPTED,
                    ExecuteRobotTask.Feedback.PHASE_VALIDATING,
                    ExecuteRobotTask.Feedback.PHASE_NAVIGATING,
                    ExecuteRobotTask.Feedback.PHASE_SENSING]
        if any(phase not in phases for phase in required):
            raise RuntimeError(f'反馈阶段不完整：{phases}')
        transform = node.buffer.lookup_transform(
            'map', 'base_link', rclpy.time.Time())
        error = math.hypot(transform.transform.translation.x - args.goal_x,
                           transform.transform.translation.y - args.goal_y)
        if error > args.position_tolerance:
            raise RuntimeError(f'导航终点误差{error:.3f} m超限')
        snapshot = wrapped.result.snapshot
        if not (snapshot.scan_available and snapshot.image_available and
                snapshot.pose_available):
            raise RuntimeError('结构化快照未声明三类数据均可用')
        if (snapshot.scan_sample_count == 0 or snapshot.image_width == 0 or
                snapshot.image_height == 0 or not snapshot.image_encoding):
            raise RuntimeError('结构化快照元数据不完整')
        if snapshot.header.frame_id != 'map':
            raise RuntimeError(f'快照Frame异常：{snapshot.header.frame_id}')
        print('M6-W5到点感知与结果检查通过')
        compact_phases = list(dict.fromkeys(phases))
        print(f'- 任务阶段完整：{compact_phases}，反馈总数{len(phases)}')
        print(f'- 公共导航实际到点，位置误差{error:.3f} m')
        print(f'- 快照：雷达{snapshot.scan_sample_count}点，最近有效距离'
              f'{snapshot.scan_min_range_m:.3f} m；图像{snapshot.image_width}x'
              f'{snapshot.image_height} {snapshot.image_encoding}；位姿可用')
        return 0
    except (RuntimeError, Exception) as error:
        print(f'M6-W5到点感知与结果检查失败：{error}')
        return 1
    finally:
        node.zero.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
