#!/usr/bin/env python3
"""运行时验证M3 IMU公共接口的静止数据、频率与契约。"""
import math
import statistics
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu


def main():
    rclpy.init(); node=Node('m3_imu_check')
    qos=QoSProfile(depth=20,reliability=ReliabilityPolicy.BEST_EFFORT)
    messages=[]; arrivals=[]; start=time.monotonic()
    node.create_subscription(Imu,'/robot/imu/data',lambda msg:(messages.append(msg),arrivals.append(time.monotonic())),qos)
    while len(messages)<120 and time.monotonic()-start<10: rclpy.spin_once(node,timeout_sec=0.1)
    try:
        if len(messages)<80: raise RuntimeError(f'消息不足：{len(messages)}')
        rate=(len(arrivals)-1)/(arrivals[-1]-arrivals[0]); sample=messages[-80:]
        values=[]
        for msg in sample:
            values.extend([msg.orientation.x,msg.orientation.y,msg.orientation.z,msg.orientation.w,
                msg.angular_velocity.x,msg.angular_velocity.y,msg.angular_velocity.z,
                msg.linear_acceleration.x,msg.linear_acceleration.y,msg.linear_acceleration.z])
        if not all(math.isfinite(value) for value in values): raise RuntimeError('存在非有限数值')
        if messages[-1].header.frame_id!='imu_link': raise RuntimeError('Frame错误')
        if rate<45: raise RuntimeError(f'墙钟频率过低：{rate:.3f}')
        angular=[math.sqrt(m.angular_velocity.x**2+m.angular_velocity.y**2+m.angular_velocity.z**2) for m in sample]
        if statistics.mean(angular)>0.02: raise RuntimeError('静止角速度过大')
        z=statistics.mean(m.linear_acceleration.z for m in sample)
        if not 9.6<z<10.0: raise RuntimeError(f'静止Z轴加速度异常：{z:.3f}')
        q=messages[-1].orientation; norm=math.sqrt(q.x*q.x+q.y*q.y+q.z*q.z+q.w*q.w)
        if not 0.99<norm<1.01: raise RuntimeError(f'四元数未归一化：{norm:.6f}')
        expected=([0.0001,0,0,0,0.0001,0,0,0,0.0001],[0.000004,0,0,0,0.000004,0,0,0,0.000004],[0.0004,0,0,0,0.0004,0,0,0,0.0004])
        actual=(messages[-1].orientation_covariance,messages[-1].angular_velocity_covariance,messages[-1].linear_acceleration_covariance)
        if any(list(a)!=list(e) for a,e in zip(actual,expected)): raise RuntimeError('协方差不符合基线')
        print('M3 IMU静止运行检查通过'); print(f'- 墙钟频率：{rate:.3f} Hz'); print(f'- Frame：{messages[-1].header.frame_id}')
        print(f'- 平均角速度模：{statistics.mean(angular):.6f} rad/s'); print(f'- 平均Z轴加速度：{z:.4f} m/s²'); print(f'- 四元数模：{norm:.6f}')
        return 0
    except RuntimeError as error: print(f'M3 IMU静止运行检查失败：{error}'); return 1
    finally: node.destroy_node(); rclpy.shutdown()


if __name__=='__main__': raise SystemExit(main())
