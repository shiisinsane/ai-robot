import rclpy
from rclpy.node import Node
from std_msgs.msg import String


def make_status_message():
    return "ai-robot M0 Python node ready"


class StatusPublisher(Node):

    def __init__(self):
        super().__init__("py_status_publisher")
        self.publisher = self.create_publisher(String, "m0/py_status", 10)
        self.timer = self.create_timer(0.5, self.publish_status)

    def publish_status(self):
        message = String()
        message.data = make_status_message()
        self.publisher.publish(message)


def main(args=None):
    rclpy.init(args=args)
    node = StatusPublisher()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
