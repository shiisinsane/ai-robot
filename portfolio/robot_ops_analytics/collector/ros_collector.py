"""W3 只读 ROS 2 采集节点；不创建控制 Publisher。"""

import json
import math
from pathlib import Path

from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, String

from .core import JsonlSink, TelemetryBucketAggregator


def _stamp(message):
    value = message.header.stamp
    return float(value.sec) + float(value.nanosec) / 1e9


def _yaw(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                      1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def _uint8(value):
    """兼容 Humble 中 uint8 字段可能表现为单字节 bytes。"""
    if isinstance(value, (bytes, bytearray)):
        return value[0]
    return int(value)


class RosCollector(Node):
    """监听遥测及编排上下文，输出可追溯 JSONL。"""

    def __init__(self):
        super().__init__("roa_w3_collector")
        self.declare_parameter("output_path", "w3_records.jsonl")
        self._sink = JsonlSink(Path(str(self.get_parameter("output_path").value)))
        self._aggregator = TelemetryBucketAggregator()
        self._task_id = None
        self._written_buckets = set()
        self._partial_start_buckets = set()
        self._partial_end_buckets = set()
        self._task_started_at = {}
        sensor_qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
        state_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        latched_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                                 durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(
            String, "analytics/task_context", self._task_context_callback, state_qos)
        self.create_subscription(Odometry, "odom", self._odom, state_qos)
        self.create_subscription(PoseWithCovarianceStamped, "pose", self._pose, state_qos)
        self.create_subscription(LaserScan, "scan", self._scan, sensor_qos)
        self.create_subscription(Bool, "safety/stop_active", self._safety, latched_qos)
        self.create_subscription(DiagnosticArray, "diagnostics", self._diagnostics, state_qos)
        self.create_timer(1.0, self._flush)

    def _task_context_callback(self, message):
        context = json.loads(message.data)
        active = context.get("active", True)
        next_task_id = context.get("task_id") if active else None
        if not active:
            ended_task_id = context.get("task_id") or self._task_id
            ended_at = float(context.get(
                "event_time_sim", self.get_clock().now().nanoseconds / 1e9))
            if ended_task_id:
                self._partial_end_buckets.add((ended_task_id, math.floor(ended_at)))
            self._flush(force=True)
        if next_task_id and next_task_id != self._task_id:
            now = self.get_clock().now().nanoseconds / 1e9
            self._partial_start_buckets.add((next_task_id, math.floor(now)))
            self._task_started_at[next_task_id] = now
        self._task_id = next_task_id
        self._sink.append("task_context", context)

    def _odom(self, message):
        if self._task_id:
            self._aggregator.add_odom(self._task_id, _stamp(message),
                                      message.twist.twist.linear.x,
                                      message.twist.twist.angular.z)

    def _pose(self, message):
        if self._task_id:
            pose, covariance = message.pose.pose, message.pose.covariance
            self._aggregator.add_pose(self._task_id, _stamp(message), pose.position.x,
                                      pose.position.y, _yaw(pose.orientation),
                                      covariance[0], covariance[7], covariance[35])

    def _scan(self, message):
        if self._task_id:
            self._aggregator.add_scan(self._task_id, _stamp(message), message.ranges,
                                      message.range_min, message.range_max)

    def _safety(self, message):
        if self._task_id:
            now = self.get_clock().now().nanoseconds / 1e9
            self._aggregator.add_safety(self._task_id, now, message.data)

    def _diagnostics(self, message):
        if self._task_id:
            self._sink.append("diagnostics", {
                "task_id": self._task_id,
                "event_time_sim": self.get_clock().now().nanoseconds / 1e9,
                "status": [{"name": s.name, "level": _uint8(s.level), "message": s.message}
                           for s in message.status],
            })

    def _flush(self, force=False):
        now = self.get_clock().now().nanoseconds / 1e9
        for row in self._aggregator.rows():
            key = (row["task_id"], row["bucket_start_sim"])
            started_at = self._task_started_at.get(row["task_id"])
            # 丢弃激活后才抵达的旧Header桶，以及不足一秒的任务首桶。
            if ((started_at is not None and row["bucket_end_sim"] <= started_at) or
                    key in self._partial_start_buckets or
                    key in self._partial_end_buckets):
                self._written_buckets.add(key)
                continue
            # 当前秒仍可能继续收到样本，只在桶结束后写入；终态时强制收尾。
            if key not in self._written_buckets and (force or row["bucket_end_sim"] <= now):
                self._sink.append("task_telemetry_1s", row)
                self._written_buckets.add(key)


def main():
    rclpy.init()
    node = RosCollector()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
