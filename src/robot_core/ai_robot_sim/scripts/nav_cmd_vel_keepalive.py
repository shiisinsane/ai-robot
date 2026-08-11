#!/usr/bin/env python3
"""将Nav2速度命令接入M4安全入口，并在恢复切换期间保持零速心跳。"""

import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


def command_is_fresh(last_seen, now, timeout=0.15):
    return last_seen is not None and now - last_seen < timeout


class NavCmdVelKeepalive(Node):
    def __init__(self):
        super().__init__('nav_cmd_vel_keepalive')
        self._last_seen = None
        self._last_command = Twist()
        self._publisher = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.create_subscription(
            Twist, '/robot/internal/nav_cmd_vel', self._on_command, 10)
        self.create_timer(0.05, self._publish)

    def _on_command(self, message):
        self._last_seen = time.monotonic()
        self._last_command = message
        self._publisher.publish(message)

    def _publish(self):
        if command_is_fresh(self._last_seen, time.monotonic()):
            self._publisher.publish(self._last_command)
        else:
            self._publisher.publish(Twist())


def main(args=None):
    rclpy.init(args=args)
    node = NavCmdVelKeepalive()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
