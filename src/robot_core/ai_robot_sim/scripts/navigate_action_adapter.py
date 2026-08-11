#!/usr/bin/env python3
"""将M1公共NavigateToPose Action薄适配到Nav2内部Action，并传播取消。"""

import rclpy
from action_msgs.msg import GoalStatus
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node


class NavigateActionAdapter(Node):
    def __init__(self):
        super().__init__('navigate_action_adapter')
        group = ReentrantCallbackGroup()
        self.client = ActionClient(
            self, NavigateToPose, '/robot/navigate_to_pose', callback_group=group)
        self.internal_handles = {}
        self.cancel_requested = set()
        self.server = ActionServer(
            self, NavigateToPose, '/robot/navigation/navigate_to_pose',
            execute_callback=self.execute,
            goal_callback=lambda _: GoalResponse.ACCEPT,
            cancel_callback=self.cancel,
            callback_group=group)

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
        if wrapped.status == GoalStatus.STATUS_SUCCEEDED:
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
