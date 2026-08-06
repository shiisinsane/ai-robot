#!/usr/bin/env python3
"""将控制器内部Transient Local关节状态适配为公共Volatile契约。"""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import JointState


class JointStateQosAdapter(Node):
    def __init__(self):
        super().__init__('joint_state_qos_adapter')
        input_qos = QoSProfile(
            depth=10, reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL)
        output_qos = QoSProfile(
            depth=10, reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE)
        self._publisher = self.create_publisher(
            JointState, '/robot/joint_states', output_qos)
        self.create_subscription(
            JointState, '/robot/joint_state_broadcaster/joint_states',
            self._publisher.publish, input_qos)


def main(args=None):
    rclpy.init(args=args)
    node = JointStateQosAdapter()
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
