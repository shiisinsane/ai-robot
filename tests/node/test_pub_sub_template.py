"""节点测试模板：在进程内验证ROS 2 Publisher/Subscriber通信。"""

import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from std_msgs.msg import String


def test_nodes_exchange_message_with_explicit_qos():
    rclpy.init()
    publisher_node = rclpy.create_node("w6_test_publisher")
    subscriber_node = rclpy.create_node("w6_test_subscriber")
    executor = SingleThreadedExecutor()
    executor.add_node(publisher_node)
    executor.add_node(subscriber_node)
    received = []
    qos = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )
    publisher = publisher_node.create_publisher(String, "w6/node_test", qos)
    subscription = subscriber_node.create_subscription(
        String, "w6/node_test", received.append, qos
    )

    try:
        deadline = time.monotonic() + 3.0
        message = String()
        message.data = "w6-ready"
        while time.monotonic() < deadline and not received:
            publisher.publish(message)
            executor.spin_once(timeout_sec=0.1)
        assert received and received[-1].data == "w6-ready"
    finally:
        subscriber_node.destroy_subscription(subscription)
        publisher_node.destroy_publisher(publisher)
        executor.remove_node(subscriber_node)
        executor.remove_node(publisher_node)
        subscriber_node.destroy_node()
        publisher_node.destroy_node()
        executor.shutdown()
        rclpy.shutdown()
