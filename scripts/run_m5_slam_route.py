#!/usr/bin/env python3
"""以受监督低速命令执行一圈方形SLAM验证路线，并始终以零速度收尾。"""

import math
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_srvs.srv import Trigger


class RouteRunner(Node):
    def __init__(self):
        super().__init__('m5_slam_route_runner')
        self.publisher = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.clear_client = self.create_client(Trigger, '/robot/safety/clear_faults')

    def publish_for(self, linear, angular, duration):
        message = Twist()
        message.linear.x = linear
        message.angular.z = angular
        deadline = time.monotonic() + duration
        while rclpy.ok() and time.monotonic() < deadline:
            self.publisher.publish(message)
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.08)

    def stop(self, duration=0.8):
        self.publish_for(0.0, 0.0, duration)

    def clear_faults(self):
        if not self.clear_client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError('安全故障清除Service不可用')
        future = self.clear_client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        if not future.done() or not future.result().success:
            message = future.result().message if future.done() else '调用超时'
            raise RuntimeError(f'安全故障清除失败：{message}')


def main():
    rclpy.init()
    node = RouteRunner()
    try:
        node.stop(1.0)
        node.clear_faults()
        print('安全链已就绪，开始低速方形闭环路线', flush=True)
        for index in range(4):
            node.publish_for(0.25, 0.0, 4.0)
            node.stop(0.4)
            node.publish_for(0.0, 0.5, math.pi)
            node.stop(0.4)
            print(f'已完成第{index + 1}/4条边', flush=True)
        print('M5-W3方形闭环路线完成', flush=True)
        return 0
    except (KeyboardInterrupt, RuntimeError) as error:
        print(f'M5-W3路线中止：{error}', flush=True)
        return 1
    finally:
        node.stop(1.0)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
