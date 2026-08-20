"""通过冻结的 ExecuteRobotTask Action 执行单个 W3 仿真任务。"""

import argparse
import json
import math
import time
import uuid

from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, String
from robot_interfaces.action import ExecuteRobotTask


class ExperimentRunner(Node):
    def __init__(self, args):
        super().__init__("roa_w3_experiment_runner")
        self.args = args
        self.client = ActionClient(self, ExecuteRobotTask, "task/execute")
        self._context_publisher = self.create_publisher(
            String, "analytics/task_context", 10)
        self.done = False
        self.outcome_ok = False
        self._seen = set()
        self._safety_stop = True
        self._clock_values = []
        state_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        sensor_qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
        latched_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                                 durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(Odometry, "odom", lambda _: self._mark("odom"), state_qos)
        self.create_subscription(PoseWithCovarianceStamped, "pose", lambda _: self._mark("pose"), state_qos)
        self.create_subscription(LaserScan, "scan", lambda _: self._mark("scan"), sensor_qos)
        self.create_subscription(Bool, "safety/stop_active", self._safety, latched_qos)
        self.create_subscription(DiagnosticArray, "diagnostics", lambda _: self._mark("diagnostics"), state_qos)
        self.create_timer(0.1, self._sample_clock)

    def _mark(self, name):
        self._seen.add(name)

    def _safety(self, message):
        self._safety_stop = bool(message.data)
        self._mark("safety")

    def _sample_clock(self):
        self._clock_values.append(self.get_clock().now().nanoseconds)
        self._clock_values = self._clock_values[-2:]

    def _wait_ready(self, timeout_sec=15.0):
        required = {"odom", "pose", "scan", "safety", "diagnostics"}
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            clock_advancing = (len(self._clock_values) == 2 and
                               self._clock_values[1] > self._clock_values[0])
            if required <= self._seen and clock_advancing and not self._safety_stop:
                return
        missing = sorted(required - self._seen)
        raise RuntimeError(
            f"机器人未进入 Ready：缺失 Topic={missing}、仿真时钟未推进或安全停车仍激活")

    def _wait_collector(self, timeout_sec=5.0):
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self.count_subscribers("analytics/task_context") >= 1:
                return
            rclpy.spin_once(self, timeout_sec=0.1)
        raise RuntimeError("W3采集器未订阅 analytics/task_context，拒绝发送任务")

    def start(self):
        if not self.client.wait_for_server(timeout_sec=10.0):
            raise RuntimeError("公共任务 Action /robot/task/execute 不可用")
        self._wait_ready()
        self._wait_collector()
        goal = ExecuteRobotTask.Goal()
        goal.task_id = self.args.task_id
        goal.task_type = ExecuteRobotTask.Goal.TASK_NAVIGATE_AND_SENSE
        goal.sensing_mode = ExecuteRobotTask.Goal.SENSING_BASIC_SNAPSHOT
        goal.task_timeout_sec = self.args.timeout
        goal.target_pose.header.frame_id = "map"
        goal.target_pose.header.stamp = self.get_clock().now().to_msg()
        goal.target_pose.pose.position.x = self.args.x
        goal.target_pose.pose.position.y = self.args.y
        goal.target_pose.pose.orientation.z = math.sin(self.args.yaw / 2.0)
        goal.target_pose.pose.orientation.w = math.cos(self.args.yaw / 2.0)
        self._publish_context(True, "requested")
        future = self.client.send_goal_async(goal, feedback_callback=self._feedback)
        future.add_done_callback(self._accepted)

    def _publish_context(self, active, event, **extra):
        message = String()
        message.data = json.dumps({
            "active": active, "event": event, "experiment_id": self.args.experiment_id,
            "task_id": self.args.task_id, "request_id": self.args.request_id,
            "event_time_sim": self.get_clock().now().nanoseconds / 1e9, **extra,
        }, ensure_ascii=False, sort_keys=True)
        self._context_publisher.publish(message)

    def _feedback(self, message):
        feedback = message.feedback
        self._publish_context(True, "feedback", phase=int(feedback.phase),
                              progress=float(feedback.progress), message=feedback.message)

    def _accepted(self, future):
        handle = future.result()
        if not handle.accepted:
            self._publish_context(False, "rejected", rejection_reason="Action 服务端拒绝目标")
            self.done = True
            return
        self._publish_context(True, "accepted")
        result = handle.get_result_async(); result.add_done_callback(self._result)

    def _result(self, future):
        wrapped = future.result(); result = wrapped.result
        self._publish_context(False, "terminal", action_status=int(wrapped.status),
                              success=bool(result.success), error_code=int(result.error_code),
                              message=result.message)
        self.outcome_ok = bool(result.success)
        self.done = True


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--request-id", default=str(uuid.uuid4()))
    parser.add_argument("--x", required=True, type=float)
    parser.add_argument("--y", required=True, type=float)
    parser.add_argument("--yaw", default=0.0, type=float)
    parser.add_argument("--timeout", default=120.0, type=float)
    return parser.parse_known_args()


def main():
    args, ros_args = arguments(); rclpy.init(args=ros_args); node = ExperimentRunner(args); node.start()
    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.destroy_node(); rclpy.shutdown()
    return 0 if node.outcome_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
