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
from std_srvs.srv import Trigger
from lifecycle_msgs.srv import GetState
from robot_interfaces.action import ExecuteRobotTask

from portfolio.robot_ops_analytics.collector.core import (
    PreacceptanceSnapshotError, build_preacceptance_snapshot, preacceptance_message_ages)


class ExperimentRunner(Node):
    def __init__(self, args):
        super().__init__("roa_w3_experiment_runner")
        self.args = args
        self.client = ActionClient(self, ExecuteRobotTask, "task/execute")
        self._clear_faults = self.create_client(Trigger, "safety/clear_faults")
        self._context_publisher = self.create_publisher(
            String, "analytics/task_context", 10)
        self.done = False
        self.outcome_ok = False
        self._seen = set()
        self._latest = {}
        self._safety_stop = True
        self._clock_values = []
        state_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        sensor_qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
        latched_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                                 durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(Odometry, "odom", self._odom, state_qos)
        self.create_subscription(PoseWithCovarianceStamped, "pose", self._pose, state_qos)
        self.create_subscription(LaserScan, "scan", self._scan, sensor_qos)
        self.create_subscription(Bool, "safety/stop_active", self._safety, latched_qos)
        self.create_subscription(DiagnosticArray, "diagnostics", self._diagnostics, state_qos)
        self._lifecycle_clients = {name: self.create_client(GetState, f"{name}/get_state")
                                   for name in ("map_server", "planner_server",
                                                "controller_server", "bt_navigator")}
        self.create_timer(0.1, self._sample_clock)

    def _mark(self, name):
        self._seen.add(name)

    @staticmethod
    def _stamp(message):
        return float(message.header.stamp.sec) + float(message.header.stamp.nanosec) / 1e9

    def _odom(self, message):
        self._latest["odom"] = {"stamp_sim": self._stamp(message)}
        self._mark("odom")

    def _pose(self, message):
        covariance = message.pose.covariance
        self._latest["pose"] = {"stamp_sim": self._stamp(message),
                                "covariance_x": covariance[0], "covariance_y": covariance[7],
                                "covariance_yaw": covariance[35]}
        self._mark("pose")

    def _scan(self, message):
        self._latest["scan"] = {"stamp_sim": self._stamp(message)}
        self._mark("scan")

    def _diagnostics(self, _message):
        self._latest["diagnostics"] = {
            "stamp_sim": self.get_clock().now().nanoseconds / 1e9}
        self._mark("diagnostics")

    def _safety(self, message):
        self._safety_stop = bool(message.data)
        self._latest["safety"] = {
            "stamp_sim": self.get_clock().now().nanoseconds / 1e9,
            "active": self._safety_stop}
        self._mark("safety")

    def _navigation_nodes_active(self):
        for name, client in self._lifecycle_clients.items():
            if not client.wait_for_service(timeout_sec=2.0):
                raise RuntimeError(f"Nav2生命周期服务不可用：{name}/get_state")
            future = client.call_async(GetState.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=2.0)
            response = future.result() if future.done() else None
            if response is None or int(response.current_state.id) != 3:
                return False
        return True

    def _sample_clock(self):
        self._clock_values.append(self.get_clock().now().nanoseconds)
        self._clock_values = self._clock_values[-2:]

    def _wait_ready(self, timeout_sec=30.0):
        required = {"odom", "pose", "scan", "safety", "diagnostics"}
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            clock_advancing = (len(self._clock_values) == 2 and
                               self._clock_values[1] > self._clock_values[0])
            if required <= self._seen and clock_advancing:
                break
        else:
            missing = sorted(required - self._seen)
            raise RuntimeError(
                f"机器人未进入 Ready：缺失 Topic={missing}或仿真时钟未推进")

        if not self._clear_faults.wait_for_service(timeout_sec=3.0):
            raise RuntimeError("安全故障清除服务不可用")
        last_message = "未调用"
        for _ in range(5):
            future = self._clear_faults.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=2.0)
            response = future.result() if future.done() else None
            if response is not None:
                last_message = response.message
            if response is not None and response.success:
                false_deadline = time.monotonic() + 1.0
                while time.monotonic() < false_deadline:
                    rclpy.spin_once(self, timeout_sec=0.02)
                    if not self._safety_stop:
                        return
            rclpy.spin_once(self, timeout_sec=0.1)
        raise RuntimeError(
            f"Runner内安全清除失败或停车状态未解除：{last_message}")

    def _wait_collector(self, timeout_sec=5.0):
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self.count_subscribers("analytics/task_context") >= 1:
                return
            rclpy.spin_once(self, timeout_sec=0.1)
        raise RuntimeError("W3采集器未订阅 analytics/task_context，拒绝发送任务")

    def _warm_task_telemetry(self, duration_sec=0.5):
        """给采集器留出任务内传感器窗口，覆盖立即失败的导航。"""
        deadline = time.monotonic() + duration_sec
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)

    def _wait_coherent_snapshot_time(self, freshness_sec, timeout_sec=2.0):
        """等待ROS时钟与最新传感器消息形成一致截面，不放宽新鲜度门限。"""
        deadline = time.monotonic() + timeout_sec
        last_error = None
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.02)
            now_sim = self.get_clock().now().nanoseconds / 1e9
            try:
                preacceptance_message_ages(
                    now_sim=now_sim, messages=self._latest, freshness_sec=freshness_sec)
                return now_sim
            except (PreacceptanceSnapshotError, KeyError) as error:
                last_error = error
        raise PreacceptanceSnapshotError(
            f"任务前消息与仿真时钟未在{timeout_sec}秒内形成一致截面：{last_error}")

    def start(self):
        if not self.client.wait_for_server(timeout_sec=10.0):
            raise RuntimeError("公共任务 Action /robot/task/execute 不可用")
        self._wait_collector()
        self._wait_ready()
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
        if self.args.preacceptance_snapshot_required:
            freshness_sec = {"odom": 0.2, "pose": 0.5, "scan": 0.5, "safety": 0.3}
            # 生命周期查询会spin当前节点并接收新的传感器回调。必须先完成该查询，
            # 再冻结最终消息/时钟截面，否则新消息可能相对旧now_sim呈现负年龄。
            navigation_nodes_active = self._navigation_nodes_active()
            now_sim = self._wait_coherent_snapshot_time(freshness_sec)
            snapshot = build_preacceptance_snapshot(
                now_sim=now_sim, messages=self._latest,
                freshness_sec=freshness_sec,
                metadata={"dataset_version": self.args.dataset_version,
                          "experiment_id": self.args.experiment_id, "task_id": self.args.task_id,
                          "request_id": self.args.request_id, "source_batch_id": self.args.source_batch_id,
                          "route_id": self.args.route_id, "obstacle_profile": self.args.obstacle_profile,
                          "localization_perturbation_level": self.args.localization_perturbation_level,
                          "parameter_version": self.args.parameter_version,
                          "start_x_m": self.args.start_x, "start_y_m": self.args.start_y,
                          "start_yaw_rad": self.args.start_yaw, "target_x_m": self.args.x,
                          "target_y_m": self.args.y, "target_yaw_rad": self.args.yaw},
                history={"prior_task_count_window_10": self.args.prior_task_count_window_10,
                         "prior_failure_count_window_10": self.args.prior_failure_count_window_10,
                         "prior_timeout_count_window_10": self.args.prior_timeout_count_window_10,
                         "no_history": self.args.no_history},
                navigation_nodes_active=navigation_nodes_active)
            self._publish_context(True, "preacceptance_snapshot", snapshot=snapshot)
        self._publish_context(True, "requested")
        self._warm_task_telemetry()
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
    parser.add_argument("--dataset-version", default="roa-data-v0.1")
    parser.add_argument("--source-batch-id", default="legacy-unspecified")
    parser.add_argument("--route-id", default="legacy-unspecified")
    parser.add_argument("--obstacle-profile", default="legacy-unspecified")
    parser.add_argument("--localization-perturbation-level", default="legacy-unspecified")
    parser.add_argument("--parameter-version", default="baseline")
    parser.add_argument("--start-x", default=0.0, type=float)
    parser.add_argument("--start-y", default=0.0, type=float)
    parser.add_argument("--start-yaw", default=0.0, type=float)
    parser.add_argument("--prior-task-count-window-10", default=0, type=int)
    parser.add_argument("--prior-failure-count-window-10", default=0, type=int)
    parser.add_argument("--prior-timeout-count-window-10", default=0, type=int)
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--preacceptance-snapshot-required", action="store_true",
                        help="B2正式任务必须启用；旧版复现默认不改变记录契约")
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
