#!/usr/bin/env python3
"""执行M6-W8五次综合任务并核对成功率、精度、耗时和快照一致性。"""

import argparse
import math
import statistics
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


def yaw_of(quaternion):
    return math.atan2(
        2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1.0 - 2.0 * (quaternion.y * quaternion.y + quaternion.z * quaternion.z))


def angle_error(left, right):
    return math.atan2(math.sin(left - right), math.cos(left - right))


class RepeatedTaskCheck(Node):
    def __init__(self):
        super().__init__('m6_w8_repeated_task_check')
        self.client = ActionClient(self, ExecuteRobotTask, '/robot/task/execute')
        self.zero = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.clear = self.create_client(Trigger, '/robot/safety/clear_faults')
        self.stop_active = True
        self.navigation_status = []
        self.create_subscription(
            Bool, '/robot/safety/stop_active',
            lambda message: setattr(self, 'stop_active', message.data), 20)
        self.create_subscription(
            GoalStatusArray, '/robot/navigation/navigate_to_pose/_action/status',
            lambda message: setattr(self, 'navigation_status', message.status_list), 20)
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)

    def prepare(self):
        if not self.client.wait_for_server(timeout_sec=30.0):
            raise RuntimeError('公共任务Action不可用')
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
                    self.zero.publish(Twist())
                    rclpy.spin_once(self, timeout_sec=0.05)
                if not self.stop_active:
                    for _ in range(2):
                        rclpy.spin_once(self, timeout_sec=0.05)
                    return
        raise RuntimeError('安全故障清除失败')

    def run(self, index, target, timeout):
        x, y, yaw = target
        goal = ExecuteRobotTask.Goal()
        goal.task_id = f'm6-w8-round-{index + 1}'
        goal.task_type = goal.TASK_NAVIGATE_AND_SENSE
        goal.target_pose.header.frame_id = 'map'
        goal.target_pose.pose.position.x = x
        goal.target_pose.pose.position.y = y
        goal.target_pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.target_pose.pose.orientation.w = math.cos(yaw / 2.0)
        goal.sensing_mode = goal.SENSING_BASIC_SNAPSHOT
        goal.task_timeout_sec = timeout
        phases = []
        started = time.monotonic()
        sent = self.client.send_goal_async(
            goal, feedback_callback=lambda message: phases.append(
                message.feedback.phase))
        rclpy.spin_until_future_complete(self, sent, timeout_sec=5.0)
        if not sent.done() or not sent.result() or not sent.result().accepted:
            return False, time.monotonic() - started, math.inf, math.inf, '目标未接受'
        result = sent.result().get_result_async()
        rclpy.spin_until_future_complete(self, result, timeout_sec=timeout + 5.0)
        elapsed = time.monotonic() - started
        if not result.done() or not result.result():
            return False, elapsed, math.inf, math.inf, '结果超时'
        wrapped = result.result()
        for _ in range(5):
            rclpy.spin_once(self, timeout_sec=0.1)
        transform = self.buffer.lookup_transform('map', 'base_link', rclpy.time.Time())
        position = math.hypot(
            transform.transform.translation.x - x,
            transform.transform.translation.y - y)
        heading = abs(angle_error(yaw_of(transform.transform.rotation), yaw))
        snapshot = wrapped.result.snapshot
        expected_phases = {
            ExecuteRobotTask.Feedback.PHASE_ACCEPTED,
            ExecuteRobotTask.Feedback.PHASE_VALIDATING,
            ExecuteRobotTask.Feedback.PHASE_NAVIGATING,
            ExecuteRobotTask.Feedback.PHASE_SENSING,
        }
        valid = (
            wrapped.status == GoalStatus.STATUS_SUCCEEDED and
            wrapped.result.success and
            wrapped.result.error_code == ExecuteRobotTask.Result.ERROR_NONE and
            expected_phases <= set(phases) and
            snapshot.scan_available and snapshot.scan_sample_count == 360 and
            snapshot.image_available and snapshot.image_width == 640 and
            snapshot.image_height == 480 and snapshot.image_encoding == 'rgb8' and
            snapshot.pose_available)
        detail = (f'Action={wrapped.status}，错误={wrapped.result.error_code}，'
                  f'阶段={list(dict.fromkeys(phases))}，'
                  f'雷达={snapshot.scan_sample_count}，图像={snapshot.image_width}x'
                  f'{snapshot.image_height} {snapshot.image_encoding}')
        return valid, elapsed, position, heading, detail

    def no_active_navigation(self):
        return not any(item.status in (
            GoalStatus.STATUS_ACCEPTED, GoalStatus.STATUS_EXECUTING,
            GoalStatus.STATUS_CANCELING) for item in self.navigation_status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=5)
    parser.add_argument('--timeout', type=float, default=90.0)
    args = parser.parse_args()
    if args.count < 5:
        print('M6-W8重复任务检查失败：正式检查次数不得少于5次')
        return 1
    rclpy.init()
    node = RepeatedTaskCheck()
    try:
        node.prepare()
        goals = ((0.8, 0.0, 0.0), (0.0, 0.0, 0.0))
        records = []
        for index in range(args.count):
            record = node.run(index, goals[index % 2], args.timeout)
            records.append(record)
            print(f'- 第{index + 1}次：成功={record[0]}，耗时={record[1]:.3f} s，'
                  f'位置误差={record[2]:.3f} m，角度误差={record[3]:.3f} rad，'
                  f'{record[4]}', flush=True)
            if not record[0]:
                break
        failures = []
        if len(records) != args.count or not all(item[0] for item in records):
            failures.append(f'成功次数{sum(item[0] for item in records)}/{args.count}')
        if any(item[2] > 0.15 for item in records):
            failures.append('位置误差超过0.15 m')
        if any(item[3] > 0.15 for item in records):
            failures.append('角度误差超过0.15 rad')
        if node.stop_active:
            failures.append('重复任务后安全停车仍激活')
        if not node.no_active_navigation():
            failures.append('重复任务后仍有活动导航目标')
        if failures:
            raise RuntimeError('；'.join(failures))
        elapsed = [item[1] for item in records]
        print(f'M6-W8重复综合任务检查通过：{args.count}/{args.count}成功')
        print(f'- 任务耗时：平均{statistics.mean(elapsed):.3f} s，'
              f'最大{max(elapsed):.3f} s')
        print(f'- 最大位置误差{max(item[2] for item in records):.3f} m，'
              f'最大角度误差{max(item[3] for item in records):.3f} rad')
        return 0
    except (RuntimeError, Exception) as error:
        print(f'M6-W8重复任务检查失败：{error}')
        return 1
    finally:
        node.zero.publish(Twist())
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
