#!/usr/bin/env python3
"""用受限原地左转验证M3 IMU正Z角速度语义。"""
import time
import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu


def main():
    rclpy.init(); node=Node('m3_imu_rotation_check'); values=[]
    qos=QoSProfile(depth=20,reliability=ReliabilityPolicy.BEST_EFFORT)
    node.create_subscription(Imu,'/robot/imu/data',lambda msg:values.append(msg.angular_velocity.z),qos)
    publisher=node.create_publisher(Twist,'/robot/cmd_vel',10); deadline=time.monotonic()+20
    try:
        while len(values)<10 and time.monotonic()<deadline: rclpy.spin_once(node,timeout_sec=0.1)
        if len(values)<10: raise RuntimeError('等待IMU超时')
        command=Twist(); command.angular.z=0.6; start=time.monotonic()
        while time.monotonic()-start<1.5:
            publisher.publish(command); rclpy.spin_once(node,timeout_sec=0.02)
        publisher.publish(Twist())
        peak=max(values[-100:])
        if peak<0.3: raise RuntimeError(f'左转时正Z角速度不足：{peak:.3f}')
        print('M3 IMU旋转符号检查通过'); print(f'- 左转峰值Z角速度：{peak:.3f} rad/s'); return 0
    except RuntimeError as error: print(f'M3 IMU旋转符号检查失败：{error}'); return 1
    finally: publisher.publish(Twist()); node.destroy_node(); rclpy.shutdown()


if __name__=='__main__': raise SystemExit(main())
