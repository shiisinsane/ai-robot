#!/usr/bin/env python3
"""将M1公共NavigateToPose Action薄适配到Nav2内部Action。"""

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
        self.server = ActionServer(
            self, NavigateToPose, '/robot/navigation/navigate_to_pose',
            execute_callback=self.execute,
            goal_callback=lambda _: GoalResponse.ACCEPT,
            cancel_callback=lambda _: CancelResponse.REJECT,
            callback_group=group)

    async def execute(self, public_handle):
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
        wrapped = await internal_handle.get_result_async()
        if wrapped.status == GoalStatus.STATUS_SUCCEEDED:
            public_handle.succeed()
        elif wrapped.status == GoalStatus.STATUS_CANCELED:
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
