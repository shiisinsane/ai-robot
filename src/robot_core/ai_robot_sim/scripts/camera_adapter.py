#!/usr/bin/env python3
"""将Gazebo相机消息规范化为M1公共RGB相机接口。"""

import copy
import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image

SENSOR_QOS = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=5,
                        reliability=ReliabilityPolicy.BEST_EFFORT)
RVIZ_QOS = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                      reliability=ReliabilityPolicy.RELIABLE)


def normalize_message(message, frame_id):
    result = copy.deepcopy(message)
    result.header.frame_id = frame_id
    return result


class CameraAdapter(Node):
    def __init__(self):
        super().__init__('camera_driver')
        self.declare_parameter('frame_id', 'camera_color_optical_frame')
        frame_id = self.get_parameter('frame_id').value
        self.image_pub = self.create_publisher(Image, 'camera/color/image_raw', SENSOR_QOS)
        self.info_pub = self.create_publisher(CameraInfo, 'camera/color/camera_info', SENSOR_QOS)
        # Humble的RViz图像插件固定请求Reliable；使用非公共调试话题适配，
        # 避免改变M1冻结的Best Effort传感器接口。
        self.rviz_image_pub = self.create_publisher(
            Image, '/ai_robot_visualization/camera/image_raw', RVIZ_QOS)
        self.image_sub = self.create_subscription(
            Image, 'image_raw', lambda msg: self._publish_image(msg, frame_id), SENSOR_QOS)
        self.info_sub = self.create_subscription(
            CameraInfo, 'camera_info_raw', lambda msg: self.info_pub.publish(normalize_message(msg, frame_id)), SENSOR_QOS)

    def _publish_image(self, message, frame_id):
        normalized = normalize_message(message, frame_id)
        self.image_pub.publish(normalized)
        self.rviz_image_pub.publish(normalized)


def main():
    rclpy.init(); node = CameraAdapter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()


if __name__ == '__main__':
    main()
