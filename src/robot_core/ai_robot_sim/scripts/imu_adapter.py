#!/usr/bin/env python3
"""将Gazebo IMU消息规范化为M1公共惯性接口。"""

import copy

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu


IMU_QOS = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=20,
    reliability=ReliabilityPolicy.BEST_EFFORT,
)


def normalize_imu(message, frame_id, orientation_covariance,
                  angular_velocity_covariance, linear_acceleration_covariance):
    result = copy.deepcopy(message)
    result.header.frame_id = frame_id
    result.orientation_covariance = orientation_covariance
    result.angular_velocity_covariance = angular_velocity_covariance
    result.linear_acceleration_covariance = linear_acceleration_covariance
    return result


class ImuAdapter(Node):
    def __init__(self):
        super().__init__('imu_driver')
        self.declare_parameter('frame_id', 'imu_link')
        self.declare_parameter('orientation_covariance', [0.0001, 0.0, 0.0, 0.0, 0.0001, 0.0, 0.0, 0.0, 0.0001])
        self.declare_parameter('angular_velocity_covariance', [0.000004, 0.0, 0.0, 0.0, 0.000004, 0.0, 0.0, 0.0, 0.000004])
        self.declare_parameter('linear_acceleration_covariance', [0.0004, 0.0, 0.0, 0.0, 0.0004, 0.0, 0.0, 0.0, 0.0004])
        frame_id = self.get_parameter('frame_id').value
        covariances = [
            self.get_parameter('orientation_covariance').value,
            self.get_parameter('angular_velocity_covariance').value,
            self.get_parameter('linear_acceleration_covariance').value,
        ]
        self.publisher = self.create_publisher(Imu, 'imu/data', IMU_QOS)
        self.subscription = self.create_subscription(
            Imu, 'imu_raw',
            lambda msg: self.publisher.publish(normalize_imu(msg, frame_id, *covariances)),
            IMU_QOS,
        )


def main():
    rclpy.init()
    node = ImuAdapter()
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
