#!/usr/bin/env python3
"""将image_proc内部输出转换为M1公共Best Effort图像接口。"""

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


INPUT_QOS = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
    reliability=ReliabilityPolicy.RELIABLE,
)
OUTPUT_QOS = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
    reliability=ReliabilityPolicy.BEST_EFFORT,
)


class ImageQosAdapter(Node):
    def __init__(self):
        super().__init__('image_qos_adapter')
        self.publisher = self.create_publisher(Image, 'image_rect', OUTPUT_QOS)
        self.subscription = self.create_subscription(
            Image, 'image_rect_internal', self.publisher.publish, INPUT_QOS)


def main():
    rclpy.init()
    node = ImageQosAdapter()
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
