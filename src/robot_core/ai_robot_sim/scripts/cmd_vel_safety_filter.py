#!/usr/bin/env python3
"""阻止非有限速度命令进入差速控制器。"""

import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


def is_finite_twist(message):
    values = (
        message.linear.x, message.linear.y, message.linear.z,
        message.angular.x, message.angular.y, message.angular.z,
    )
    return all(math.isfinite(value) for value in values)


class CmdVelSafetyFilter(Node):
    def __init__(self):
        super().__init__('cmd_vel_safety_filter')
        self._publisher = self.create_publisher(
            Twist, '/robot/controller_cmd_vel', 10)
        self.create_subscription(Twist, '/robot/cmd_vel', self._on_command, 10)

    def _on_command(self, message):
        if is_finite_twist(message):
            self._publisher.publish(message)
            return

        self.get_logger().error('拒绝非有限速度命令并发送零速度命令')
        self._publisher.publish(Twist())


def main(args=None):
    rclpy.init(args=args)
    node = CmdVelSafetyFilter()
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
