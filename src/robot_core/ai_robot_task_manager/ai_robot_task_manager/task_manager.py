"""M6-W3任务管理器骨架：目标校验、单任务、诊断和受控空实现。"""

import threading
import time

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from nav_msgs.msg import OccupancyGrid
from nav2_msgs.action import NavigateToPose
import rclpy
from action_msgs.msg import GoalStatus
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from robot_interfaces.action import ExecuteRobotTask
from std_msgs.msg import Bool

from .task_policy import map_bounds, validate_goal


class TaskManager(Node):
    """不发布速度命令的结构化任务Action服务端。"""

    def __init__(self):
        super().__init__('task_manager')
        self.declare_parameter('skeleton_delay_sec', 0.5)
        self.declare_parameter('navigation_result_sec', 240.0)
        self._group = ReentrantCallbackGroup()
        self._reserved = False
        self._lock = threading.Lock()
        self._map_bounds = None
        self._safety_stop = False
        self._phase = 'idle'
        self._task_id = ''
        self._navigation_handle = None
        self._last_navigation_feedback = 0.0
        self._navigation_progress = 0.10
        self._navigation = ActionClient(
            self, NavigateToPose, 'navigation/navigate_to_pose',
            callback_group=self._group)
        self._diagnostics = self.create_publisher(
            DiagnosticArray, 'diagnostics', 10)
        map_qos = QoSProfile(depth=1)
        map_qos.reliability = ReliabilityPolicy.RELIABLE
        map_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.create_subscription(
            OccupancyGrid, 'map', self._map_callback, map_qos,
            callback_group=self._group)
        self.create_subscription(
            Bool, 'safety/stop_active', self._safety_callback, 10,
            callback_group=self._group)
        self.create_timer(1.0, self._publish_diagnostics,
                          callback_group=self._group)
        self._server = ActionServer(
            self, ExecuteRobotTask, 'task/execute', self._execute,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=self._group)

    def _map_callback(self, message):
        self._map_bounds = map_bounds(message)

    def _safety_callback(self, message):
        self._safety_stop = message.data

    def _goal_callback(self, _request):
        with self._lock:
            if self._reserved:
                self.get_logger().warning('拒绝并发任务：已有活动任务')
                return GoalResponse.REJECT
            self._reserved = True
        return GoalResponse.ACCEPT

    @staticmethod
    def _cancel_callback(_goal_handle):
        return CancelResponse.ACCEPT

    def _feedback(self, handle, phase, progress, message, started):
        feedback = ExecuteRobotTask.Feedback()
        feedback.phase = phase
        feedback.progress = progress
        feedback.message = message
        elapsed = max(0.0, time.monotonic() - started)
        feedback.elapsed_time.sec = int(elapsed)
        feedback.elapsed_time.nanosec = int((elapsed % 1.0) * 1e9)
        handle.publish_feedback(feedback)

    def _failure(self, handle, code, message):
        result = ExecuteRobotTask.Result()
        result.success = False
        result.error_code = code
        result.message = message
        handle.abort()
        self._phase = 'failed'
        return result

    @staticmethod
    def _wait_future(future, deadline):
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.02)
        return future.done()

    def _cancel_navigation(self, deadline):
        if self._navigation_handle is None:
            return True
        future = self._navigation_handle.cancel_goal_async()
        return self._wait_future(future, deadline)

    def _navigation_feedback(self, handle, started, message):
        now = time.monotonic()
        if now - self._last_navigation_feedback < 0.2:
            return
        self._last_navigation_feedback = now
        distance = max(0.0, float(message.feedback.distance_remaining))
        # Nav2不提供总路径长度；反馈进度保持在导航阶段范围内并单调近似。
        progress = max(self._navigation_progress,
                       max(0.10, min(0.84, 0.84 - distance * 0.10)))
        self._navigation_progress = progress
        self._feedback(
            handle, ExecuteRobotTask.Feedback.PHASE_NAVIGATING,
            progress, f'导航剩余距离约{distance:.3f} m', started)

    def _navigate(self, handle, started, task_deadline):
        self._last_navigation_feedback = 0.0
        self._navigation_progress = 0.10
        if not self._navigation.wait_for_server(timeout_sec=5.0):
            return self._failure(
                handle, ExecuteRobotTask.Result.ERROR_NAVIGATION_UNAVAILABLE,
                '公共导航Action不可用')
        goal = NavigateToPose.Goal()
        goal.pose = handle.request.target_pose
        sent = self._navigation.send_goal_async(
            goal, feedback_callback=lambda message: self._navigation_feedback(
                handle, started, message))
        send_deadline = min(task_deadline, time.monotonic() + 5.0)
        if not self._wait_future(sent, send_deadline):
            return self._failure(
                handle, ExecuteRobotTask.Result.ERROR_NAVIGATION_UNAVAILABLE,
                '发送导航目标超时')
        self._navigation_handle = sent.result()
        if self._navigation_handle is None or not self._navigation_handle.accepted:
            return self._failure(
                handle, ExecuteRobotTask.Result.ERROR_NAVIGATION_UNAVAILABLE,
                '公共导航目标未接受')
        result = self._navigation_handle.get_result_async()
        nav_deadline = min(
            task_deadline, time.monotonic() +
            float(self.get_parameter('navigation_result_sec').value))
        while not result.done():
            now = time.monotonic()
            if self._safety_stop:
                self._cancel_navigation(now + 2.0)
                return self._failure(
                    handle, ExecuteRobotTask.Result.ERROR_SAFETY_STOP,
                    '导航期间安全停车已激活')
            if handle.is_cancel_requested:
                self._phase = 'canceling'
                self._feedback(
                    handle, ExecuteRobotTask.Feedback.PHASE_CANCELING,
                    0.10, '正在取消下游导航', started)
                self._cancel_navigation(now + 2.0)
                task_result = ExecuteRobotTask.Result()
                task_result.success = False
                task_result.error_code = (
                    ExecuteRobotTask.Result.ERROR_NAVIGATION_CANCELED)
                task_result.message = '任务及下游导航已取消'
                handle.canceled()
                self._phase = 'canceled'
                return task_result
            if now >= nav_deadline:
                self._cancel_navigation(now + 2.0)
                return self._failure(
                    handle, ExecuteRobotTask.Result.ERROR_TASK_TIMEOUT,
                    '任务或导航阶段超时')
            time.sleep(0.02)
        status = result.result().status
        if status == GoalStatus.STATUS_SUCCEEDED:
            self._phase = 'sensing'
            self._feedback(
                handle, ExecuteRobotTask.Feedback.PHASE_SENSING,
                0.90, '导航成功，进入到点感知', started)
            return self._failure(
                handle, ExecuteRobotTask.Result.ERROR_SENSOR_UNAVAILABLE,
                'M6-W4导航成功；到点感知将在W5接入')
        if status == GoalStatus.STATUS_CANCELED:
            return self._failure(
                handle, ExecuteRobotTask.Result.ERROR_NAVIGATION_CANCELED,
                '下游导航已取消')
        return self._failure(
            handle, ExecuteRobotTask.Result.ERROR_NAVIGATION_FAILED,
            f'下游导航失败，Action状态{status}')

    def _execute(self, handle):
        started = time.monotonic()
        self._task_id = handle.request.task_id
        try:
            self._phase = 'accepted'
            self._feedback(handle, ExecuteRobotTask.Feedback.PHASE_ACCEPTED,
                           0.0, '任务已接受', started)
            self._phase = 'validating'
            self._feedback(handle, ExecuteRobotTask.Feedback.PHASE_VALIDATING,
                           0.05, '正在校验目标', started)
            code, message = validate_goal(
                handle.request, ExecuteRobotTask.Goal.TASK_NAVIGATE_AND_SENSE,
                ExecuteRobotTask.Goal.SENSING_BASIC_SNAPSHOT, self._map_bounds)
            if code:
                return self._failure(handle, code, message)
            if self._safety_stop:
                return self._failure(
                    handle, ExecuteRobotTask.Result.ERROR_SAFETY_STOP,
                    '安全停车已激活')
            self._phase = 'navigating'
            self._feedback(
                handle, ExecuteRobotTask.Feedback.PHASE_NAVIGATING,
                0.10, '正在调用公共导航能力', started)
            deadline = started + float(handle.request.task_timeout_sec)
            return self._navigate(handle, started, deadline)
        finally:
            self._navigation_handle = None
            self._task_id = ''
            with self._lock:
                self._reserved = False

    def _publish_diagnostics(self):
        message = DiagnosticArray()
        message.header.stamp = self.get_clock().now().to_msg()
        status = DiagnosticStatus()
        status.name = 'task_manager'
        status.hardware_id = 'simulation'
        status.level = DiagnosticStatus.OK
        status.message = 'ready' if not self._reserved else self._phase
        status.values = [
            KeyValue(key='phase', value=self._phase),
            KeyValue(key='task_id', value=self._task_id),
            KeyValue(key='single_active_goal', value='true'),
            KeyValue(key='publishes_velocity', value='false'),
        ]
        message.status = [status]
        self._diagnostics.publish(message)

    def destroy_node(self):
        self._server.destroy()
        super().destroy_node()


def main():
    rclpy.init()
    node = TaskManager()
    executor = MultiThreadedExecutor(num_threads=3)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()
