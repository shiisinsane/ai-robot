"""通过已冻结公共导航Action将机器人移到W4任务起点，不生成正式任务样本。"""

import argparse
import math
import time

import rclpy
from action_msgs.msg import GoalStatus
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_srvs.srv import Trigger


class StartPreparer(Node):
    def __init__(self):
        super().__init__("roa_w4_start_preparer")
        self.navigation = ActionClient(
            self, NavigateToPose, "/robot/navigation/navigate_to_pose")
        self.clear_faults = self.create_client(
            Trigger, "/robot/safety/clear_faults")

    def run(self, x, y, yaw, timeout_sec):
        if not self.navigation.wait_for_server(timeout_sec=15.0):
            raise RuntimeError("公共导航Action不可用")
        if not self.clear_faults.wait_for_service(timeout_sec=10.0):
            raise RuntimeError("安全故障清除Service不可用")
        cleared = self.clear_faults.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, cleared, timeout_sec=10.0)
        if (not cleared.done() or cleared.result() is None or
                not cleared.result().success):
            raise RuntimeError("起点准备前安全故障清除失败")
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
        sent = self.navigation.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, sent, timeout_sec=10.0)
        if not sent.done() or sent.result() is None or not sent.result().accepted:
            raise RuntimeError("起点准备导航目标未接受")
        result = sent.result().get_result_async()
        deadline = time.monotonic() + timeout_sec
        while rclpy.ok() and not result.done() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
        if not result.done() or result.result() is None:
            sent.result().cancel_goal_async()
            raise RuntimeError("起点准备导航超时")
        if result.result().status != GoalStatus.STATUS_SUCCEEDED:
            raise RuntimeError(
                f"起点准备导航失败，Action状态{result.result().status}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x", type=float, required=True)
    parser.add_argument("--y", type=float, required=True)
    parser.add_argument("--yaw", type=float, required=True)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    rclpy.init()
    node = StartPreparer()
    try:
        node.run(args.x, args.y, args.yaw, args.timeout)
        print(f"起点准备完成：({args.x}, {args.y}, {args.yaw})")
        return 0
    except RuntimeError as error:
        print(f"起点准备失败：{error}")
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
