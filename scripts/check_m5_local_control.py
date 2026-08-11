#!/usr/bin/env python3
"""验证W7公共导航Action、实际到点、局部代价地图和安全命令链。"""

import argparse
import math
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
from nav2_msgs.action import NavigateToPose
from nav2_msgs.msg import Costmap
from rclpy.action import ActionClient
from rclpy.node import Node
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener


def yaw_from_quaternion(quaternion):
    return math.atan2(
        2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1.0 - 2.0 * (quaternion.y * quaternion.y + quaternion.z * quaternion.z))


def angle_error(left, right):
    return math.atan2(math.sin(left - right), math.cos(left - right))


class ControlCheck(Node):
    def __init__(self):
        super().__init__('m5_local_control_check')
        self.client = ActionClient(
            self, NavigateToPose, '/robot/navigation/navigate_to_pose')
        self.poses = []
        self.costmaps = []
        self.commands = []
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)
        self.zero_command = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.clear_client = self.create_client(Trigger, '/robot/safety/clear_faults')
        self.create_subscription(PoseWithCovarianceStamped, '/robot/pose',
                                 self._pose, 10)
        self.create_subscription(Costmap, '/robot/local_costmap/costmap_raw',
                                 self.costmaps.append, 10)
        self.create_subscription(Twist, '/robot/cmd_vel', self.commands.append, 10)

    def _pose(self, message):
        pose = message.pose.pose
        self.poses.append((pose.position.x, pose.position.y,
                           yaw_from_quaternion(pose.orientation)))

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--goal-x', type=float, default=1.0)
    parser.add_argument('--goal-y', type=float, default=0.0)
    parser.add_argument('--goal-yaw', type=float, default=0.0)
    parser.add_argument('--timeout', type=float, default=60.0)
    parser.add_argument('--position-tolerance', type=float, default=0.15)
    parser.add_argument('--yaw-tolerance', type=float, default=0.15)
    parser.add_argument('--obstacle-x', type=float)
    parser.add_argument('--obstacle-y', type=float)
    parser.add_argument('--minimum-center-clearance', type=float, default=0.0)
    args = parser.parse_args()
    rclpy.init()
    node = ControlCheck()
    errors = []
    try:
        if not node.client.wait_for_server(timeout_sec=30.0):
            print('M5-W7局部控制检查失败：公共导航Action不可用')
            return 1
        node.prepare_safety()
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.pose.position.x = args.goal_x
        goal.pose.pose.position.y = args.goal_y
        goal.pose.pose.orientation.z = math.sin(args.goal_yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(args.goal_yaw / 2.0)
        started = time.monotonic()
        send_future = node.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(node, send_future, timeout_sec=5.0)
        if not send_future.done() or not send_future.result().accepted:
            print('M5-W7局部控制检查失败：导航目标未接受')
            return 1
        result_future = send_future.result().get_result_async()
        rclpy.spin_until_future_complete(node, result_future, timeout_sec=args.timeout)
        elapsed = time.monotonic() - started
        if not result_future.done() or result_future.result() is None:
            errors.append('导航结果超时')
        elif result_future.result().status != 4:
            errors.append(f'导航Action状态错误：{result_future.result().status}')

        for _ in range(10):
            rclpy.spin_once(node, timeout_sec=0.1)
        try:
            transform = node.buffer.lookup_transform(
                'map', 'base_link', rclpy.time.Time())
            rotation = transform.transform.rotation
            final = (transform.transform.translation.x,
                     transform.transform.translation.y,
                     yaw_from_quaternion(rotation))
        except Exception:
            final = None
        if final is None:
            errors.append('缺少map到base_link终点TF')
            position_error = yaw_error = math.inf
        else:
            position_error = math.hypot(final[0] - args.goal_x,
                                        final[1] - args.goal_y)
            yaw_error = abs(angle_error(final[2], args.goal_yaw))
            if position_error > args.position_tolerance:
                errors.append(f'到点位置误差{position_error:.3f} m超限')
            if yaw_error > args.yaw_tolerance:
                errors.append(f'到点角度误差{yaw_error:.3f} rad超限')
        moving = [command for command in node.commands
                  if abs(command.linear.x) > 0.01 or abs(command.angular.z) > 0.01]
        if not moving:
            errors.append('未观察到Nav2运动命令')
        if not node.costmaps:
            errors.append('局部代价地图无输出')
            lethal_cells = 0
        else:
            lethal_cells = sum(value >= 253 for value in node.costmaps[-1].data)
            if lethal_cells == 0:
                errors.append('局部代价地图未标记静态障碍')

        minimum_clearance = None
        if args.obstacle_x is not None and args.obstacle_y is not None:
            minimum_clearance = min(
                (math.hypot(x - args.obstacle_x, y - args.obstacle_y)
                 for x, y, _ in node.poses), default=math.inf)
            if minimum_clearance < args.minimum_center_clearance:
                errors.append(
                    f'障碍中心最小距离{minimum_clearance:.3f} m低于门限')

        if errors:
            print('M5-W7局部控制检查失败：' + '；'.join(errors))
            return 1
        print('M5-W7局部控制检查通过')
        print(f'- 公共Action成功到点，耗时{elapsed:.3f} s')
        print(f'- 终点误差：位置{position_error:.3f} m，角度{yaw_error:.3f} rad')
        print(f'- Nav2运动命令{len(moving)}条；局部代价地图致命格{lethal_cells}个')
        if minimum_clearance is not None:
            print(f'- 障碍中心最小距离{minimum_clearance:.3f} m')
        return 0
    except RuntimeError as error:
        print(f'M5-W7局部控制检查失败：{error}')
        return 1
    finally:
        node.zero_command.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
