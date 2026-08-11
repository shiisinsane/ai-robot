#!/usr/bin/env python3
"""验证W6可达/不可达规划、全局代价地图和首次规划耗时。"""

import argparse
import math
import time

import rclpy
from nav2_msgs.action import ComputePathToPose
from nav2_msgs.msg import Costmap
from nav_msgs.msg import Path
from rclpy.action import ActionClient
from rclpy.node import Node


class PlanningCheck(Node):
    def __init__(self):
        super().__init__('m5_global_planning_check')
        self.client = ActionClient(
            self, ComputePathToPose, '/robot/compute_path_to_pose')
        self.costmaps = []
        self.create_subscription(
            Costmap, '/robot/global_costmap/costmap_raw',
            self.costmaps.append, 10)

    def plan(self, x, y, timeout):
        goal = ComputePathToPose.Goal()
        goal.goal.header.frame_id = 'map'
        goal.goal.pose.position.x = x
        goal.goal.pose.position.y = y
        goal.goal.pose.orientation.w = 1.0
        started = time.monotonic()
        future = self.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        if not future.done() or future.result() is None:
            return False, None, time.monotonic() - started, '目标响应超时'
        handle = future.result()
        if not handle.accepted:
            return False, None, time.monotonic() - started, '目标被拒绝'
        result_future = handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future, timeout_sec=timeout)
        elapsed = time.monotonic() - started
        if not result_future.done() or result_future.result() is None:
            return False, None, elapsed, '规划结果超时'
        wrapped = result_future.result()
        return wrapped.status == 4, wrapped.result.path, elapsed, str(wrapped.status)


def path_length(path):
    return sum(math.hypot(right.pose.position.x - left.pose.position.x,
                          right.pose.position.y - left.pose.position.y)
               for left, right in zip(path.poses, path.poses[1:]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reachable-x', type=float, default=1.0)
    parser.add_argument('--reachable-y', type=float, default=0.0)
    parser.add_argument('--unreachable-x', type=float, default=20.0)
    parser.add_argument('--unreachable-y', type=float, default=20.0)
    parser.add_argument('--blocked-x', type=float, default=1.70)
    parser.add_argument('--blocked-y', type=float, default=1.40)
    parser.add_argument('--timeout', type=float, default=8.0)
    parser.add_argument('--maximum-plan-time', type=float, default=2.0)
    args = parser.parse_args()
    rclpy.init()
    node = PlanningCheck()
    errors = []
    try:
        if not node.client.wait_for_server(timeout_sec=20.0):
            print('M5-W6全局规划检查失败：规划Action不可用')
            return 1
        deadline = time.monotonic() + 5.0
        while not node.costmaps and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        if not node.costmaps:
            errors.append('全局代价地图无输出')
        else:
            metadata = node.costmaps[-1].metadata
            if metadata.size_x == 0 or metadata.size_y == 0:
                errors.append('全局代价地图尺寸无效')
            lethal_cells = sum(value >= 253 for value in node.costmaps[-1].data)
            inflated_cells = sum(0 < value < 253 for value in node.costmaps[-1].data)
            if lethal_cells == 0 or inflated_cells == 0:
                errors.append('全局代价地图未标记障碍或膨胀区')

        success, path, elapsed, detail = node.plan(
            args.reachable_x, args.reachable_y, args.timeout)
        if not success or not isinstance(path, Path) or len(path.poses) < 2:
            errors.append(f'可达目标未生成路径（状态{detail}）')
            reachable_length = math.inf
        else:
            reachable_length = path_length(path)
            if reachable_length <= 0.1:
                errors.append('可达路径长度无效')
        if elapsed > args.maximum_plan_time:
            errors.append(f'首次规划耗时{elapsed:.3f} s超过门限')

        unreachable_success, unreachable_path, unreachable_elapsed, _ = node.plan(
            args.unreachable_x, args.unreachable_y, args.timeout)
        if unreachable_success and unreachable_path and unreachable_path.poses:
            errors.append('地图外不可达目标错误生成路径')

        blocked_success, blocked_path, blocked_elapsed, _ = node.plan(
            args.blocked_x, args.blocked_y, args.timeout)
        if blocked_success and blocked_path and blocked_path.poses:
            errors.append('障碍物内目标错误生成路径')

        if errors:
            print('M5-W6全局规划检查失败：' + '；'.join(errors))
            return 1
        costmap = node.costmaps[-1].metadata
        print('M5-W6全局规划检查通过')
        print(f'- 全局代价地图：{costmap.size_x}x{costmap.size_y}，'
              f'分辨率{costmap.resolution:.3f} m，致命{lethal_cells}格、'
              f'膨胀{inflated_cells}格')
        print(f'- 可达路径：{len(path.poses)}个位姿，长度{reachable_length:.3f} m，'
              f'首次规划{elapsed:.3f} s')
        print(f'- 地图外目标正确失败，响应耗时{unreachable_elapsed:.3f} s')
        print(f'- 障碍物内目标正确失败，响应耗时{blocked_elapsed:.3f} s')
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
