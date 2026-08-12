#!/usr/bin/env python3
"""将M1公共NavigateToPose Action薄适配到Nav2内部Action，并传播取消。"""

import rclpy
from action_msgs.msg import GoalStatus
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from tf2_ros import Buffer, TransformListener


class NavigateActionAdapter(Node):
    def __init__(self):
        super().__init__('navigate_action_adapter')
        group = ReentrantCallbackGroup()
        self.client = ActionClient(
            self, NavigateToPose, '/robot/navigate_to_pose', callback_group=group)
        self.internal_handles = {}
        self.cancel_requested = set()
        self.safety_aborted = set()
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self, spin_thread=False)
        self.create_subscription(
            DiagnosticArray, '/robot/diagnostics', self._diagnostics, 10,
            callback_group=group)
        self.create_timer(0.2, self._localization_watchdog,
                          callback_group=group)
        self.server = ActionServer(
            self, NavigateToPose, '/robot/navigation/navigate_to_pose',
            execute_callback=self.execute,
            goal_callback=lambda _: GoalResponse.ACCEPT,
            cancel_callback=self.cancel,
            callback_group=group)

    def _diagnostics(self, message):
        """安全停车级故障出现时终止正在执行的内部导航任务。"""
        stop_codes = {'scan_timeout', 'odom_timeout', 'imu_timeout'}
        faulted = False
        for status in message.status:
            if status.name != 'safety_supervisor':
                continue
            values = {item.key: item.value for item in status.values}
            codes = set(values.get('code', '').split(','))
            if status.level == DiagnosticStatus.ERROR and codes & stop_codes:
                faulted = True
                break
        if not faulted:
            return
        self._abort_active('安全输入超时')

    def _abort_active(self, reason):
        for key, internal_handle in list(self.internal_handles.items()):
            self.safety_aborted.add(key)
            internal_handle.cancel_goal_async()
        if self.internal_handles:
            self.get_logger().error(f'导航失败关闭：{reason}')

    def _localization_watchdog(self):
        if not self.internal_handles:
            return
        try:
            transform = self.tf_buffer.lookup_transform(
                'map', 'odom', rclpy.time.Time())
            stamp = rclpy.time.Time.from_msg(transform.header.stamp)
            age = (self.get_clock().now() - stamp).nanoseconds / 1e9
            if age > 1.0:
                self._abort_active(f'定位TF超时{age:.3f} s')
        except Exception:
            self._abort_active('定位TF不可用')

    @staticmethod
    def _goal_key(handle):
        return bytes(handle.goal_id.uuid)

    def cancel(self, public_handle):
        key = self._goal_key(public_handle)
        self.cancel_requested.add(key)
        internal_handle = self.internal_handles.get(key)
        if internal_handle is not None:
            internal_handle.cancel_goal_async()
        return CancelResponse.ACCEPT

    async def execute(self, public_handle):
        key = self._goal_key(public_handle)
        if not self.client.wait_for_server(timeout_sec=5.0):
            public_handle.abort()
            return NavigateToPose.Result()

        def forward_feedback(message):
            public_handle.publish_feedback(message.feedback)

        internal_handle = await self.client.send_goal_async(
            public_handle.request, feedback_callback=forward_feedback)
        if not internal_handle.accepted:
            public_handle.abort()
            return NavigateToPose.Result()
        self.internal_handles[key] = internal_handle
        if key in self.cancel_requested or public_handle.is_cancel_requested:
            internal_handle.cancel_goal_async()
        result_future = internal_handle.get_result_async()
        wrapped = await result_future
        self.internal_handles.pop(key, None)
        cancel_requested = key in self.cancel_requested
        self.cancel_requested.discard(key)
        safety_aborted = key in self.safety_aborted
        self.safety_aborted.discard(key)
        if safety_aborted:
            public_handle.abort()
        elif wrapped.status == GoalStatus.STATUS_SUCCEEDED:
            public_handle.succeed()
        elif (wrapped.status == GoalStatus.STATUS_CANCELED or
              cancel_requested or public_handle.is_cancel_requested):
            public_handle.canceled()
        else:
            public_handle.abort()
        return wrapped.result

    def destroy_node(self):
        self.server.destroy()
        return super().destroy_node()


def main():
    rclpy.init()
    node = NavigateActionAdapter()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
