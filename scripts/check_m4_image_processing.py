#!/usr/bin/env python3
"""验证M4-W6相机基础处理链、仿真时间延迟和故障隔离。"""

import argparse
import math
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import CameraInfo, Image


SENSOR_QOS = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)


def _stamp(message):
    return message.header.stamp.sec + message.header.stamp.nanosec * 1e-9


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


class ImageProcessingCheck(Node):
    def __init__(self):
        super().__init__('m4_image_processing_check')
        self.clock = 0.0
        self.raw = []
        self.rect = []
        self.info = []
        self.odom = []
        self.create_subscription(Clock, '/clock', self._on_clock, SENSOR_QOS)
        self.create_subscription(
            Image, '/robot/camera/color/image_raw',
            lambda message: self.raw.append((self.clock, message)), SENSOR_QOS)
        self.create_subscription(
            Image, '/robot/camera/color/image_rect',
            lambda message: self.rect.append((self.clock, message)), SENSOR_QOS)
        self.create_subscription(
            CameraInfo, '/robot/camera/color/camera_info', self.info.append, SENSOR_QOS)
        self.create_subscription(Odometry, '/robot/odom', self.odom.append, 10)

    def _on_clock(self, message):
        self.clock = message.clock.sec + message.clock.nanosec * 1e-9


def _normal_check(node):
    deadline = time.monotonic() + 30.0
    pairs = []
    while len(pairs) < 20 or not node.info:
        _require(time.monotonic() < deadline, '等待原始图像、处理图像或CameraInfo超时')
        rclpy.spin_once(node, timeout_sec=0.1)
        raw_by_stamp = {_stamp(message): (clock, message)
                        for clock, message in node.raw}
        pairs = []
        for rect_clock, rect in node.rect:
            stamp = _stamp(rect)
            if stamp in raw_by_stamp:
                raw_clock, raw = raw_by_stamp[stamp]
                pairs.append((max(0.0, rect_clock - raw_clock), raw, rect))
    _require(len(pairs) >= 20, f'同时间戳原始/处理图像配对不足：{len(pairs)}')

    latencies = [item[0] for item in pairs[-20:]]
    raw = pairs[-1][1]
    rect = pairs[-1][2]
    _require((raw.width, raw.height, raw.encoding) == (640, 480, 'rgb8'),
             '原始图像规格错误')
    _require((rect.width, rect.height, rect.encoding) == (640, 480, 'rgb8'),
             '处理图像规格未保持640x480 rgb8')
    _require(rect.header.frame_id == raw.header.frame_id ==
             'camera_color_optical_frame', '处理图像未保持光学Frame')
    _require(_stamp(rect) == _stamp(raw), '处理图像未保持原始时间戳')
    _require(rect.step == raw.step == 1920 and len(rect.data) == 640 * 480 * 3,
             '处理图像步长或数据长度错误')
    _require(all(math.isfinite(value) and value <= 0.1 for value in latencies),
             f'图像处理仿真时间延迟超过0.1秒：max={max(latencies):.6f}')

    stamps = [_stamp(message) for _, message in node.rect[-20:]]
    _require(all(right > left for left, right in zip(stamps, stamps[1:])),
             '处理图像时间戳不严格递增')
    rate = (len(stamps) - 1) / (stamps[-1] - stamps[0])
    _require(rate >= 1.0, f'处理图像未保持持续输出：{rate:.3f} Hz')

    info = node.info[-1]
    _require((info.width, info.height) == (640, 480) and
             info.header.frame_id == rect.header.frame_id,
             'CameraInfo与处理图像规格或Frame不一致')

    print('M4-W6相机基础处理链验证通过')
    print(f'- 原始/处理图像配对：{len(pairs)}')
    print(f'- 处理图像规格：{rect.width}x{rect.height} {rect.encoding}')
    print(f'- Frame：{rect.header.frame_id}')
    print(f'- 仿真时间频率：{rate:.3f} Hz')
    print(f'- 最大仿真时间处理延迟：{max(latencies):.6f} s')


def _timeout_check(node):
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    _require(len(node.raw) >= 20, '关闭处理链后原始图像未保持输出')
    _require(not node.rect, '关闭处理链后仍收到处理图像')
    _require(len(node.odom) >= 20, '关闭处理链后融合里程计未保持输出')
    print('M4-W6相机处理链故障隔离验证通过')
    print(f'- 5秒窗口原始图像消息数：{len(node.raw)}')
    print(f'- 5秒窗口处理图像消息数：{len(node.rect)}')
    print(f'- 5秒窗口融合里程计消息数：{len(node.odom)}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect-timeout', action='store_true')
    args = parser.parse_args()
    rclpy.init()
    node = ImageProcessingCheck()
    try:
        if args.expect_timeout:
            _timeout_check(node)
        else:
            _normal_check(node)
        return 0
    except RuntimeError as error:
        print(f'M4-W6相机基础处理链验证失败：{error}')
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
