#!/usr/bin/env python3
"""运行时验证M3 RGB相机图像与CameraInfo公共接口。"""
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image


def main():
    rclpy.init(); node=Node('m3_camera_check'); qos=QoSProfile(depth=5,reliability=ReliabilityPolicy.BEST_EFFORT)
    images=[]; infos=[]; start=time.monotonic()
    node.create_subscription(Image,'/robot/camera/color/image_raw',lambda m: images.append((time.monotonic(),m)),qos)
    node.create_subscription(CameraInfo,'/robot/camera/color/camera_info',lambda m: infos.append(m),qos)
    while (len(images)<30 or not infos) and time.monotonic()-start<15: rclpy.spin_once(node,timeout_sec=0.2)
    try:
        if len(images)<20 or not infos: raise RuntimeError(f'图像/参数消息不足：{len(images)}/{len(infos)}')
        image=images[-1][1]; info=infos[-1]; rate=(len(images)-1)/(images[-1][0]-images[0][0])
        if (image.width,image.height,image.encoding)!=(640,480,'rgb8'): raise RuntimeError('图像规格错误')
        if image.header.frame_id!='camera_color_optical_frame' or info.header.frame_id!=image.header.frame_id: raise RuntimeError('Frame不一致')
        if (info.width,info.height)!=(640,480) or info.k[0]<=0 or info.k[4]<=0: raise RuntimeError('CameraInfo无效')
        if rate<10: raise RuntimeError(f'墙钟频率过低：{rate:.3f}')
        if len(image.data)!=640*480*3: raise RuntimeError('图像数据长度错误')
        print('M3 RGB相机运行检查通过'); print(f'- 规格：{image.width}x{image.height} {image.encoding}')
        print(f'- 墙钟频率：{rate:.3f} Hz'); print(f'- Frame：{image.header.frame_id}'); print(f'- 焦距：fx={info.k[0]:.3f}, fy={info.k[4]:.3f}')
        return 0
    except RuntimeError as e: print(f'M3 RGB相机运行检查失败：{e}'); return 1
    finally: node.destroy_node(); rclpy.shutdown()


if __name__=='__main__': raise SystemExit(main())
