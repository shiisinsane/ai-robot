#!/usr/bin/env python3
"""限制地图保存名称和目录，并公开M1冻结的SaveMap Service。"""

import re
import time
from pathlib import Path

import rclpy
from nav2_msgs.srv import SaveMap
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node


SAFE_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')


def resolve_map_base(allowed_directory, requested_name):
    """把不含路径的安全名称解析到冻结目录。"""
    if not SAFE_NAME.fullmatch(requested_name):
        raise ValueError('地图名称只能包含字母、数字、下划线和连字符，长度1至64')
    directory = Path(allowed_directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = (directory / requested_name).resolve()
    if target.parent != directory:
        raise ValueError('地图保存目标越出允许目录')
    return target


class MapSaveGuard(Node):
    def __init__(self):
        super().__init__('map_save_guard')
        self.declare_parameter('allowed_directory', '/tmp/ai_robot_maps')
        self._group = ReentrantCallbackGroup()
        self._client = self.create_client(
            SaveMap, '/robot/internal_map_saver/save_map', callback_group=self._group)
        self._service = self.create_service(
            SaveMap, '/robot/map/save_map', self._save, callback_group=self._group)

    def _save(self, request, response):
        try:
            target = resolve_map_base(
                self.get_parameter('allowed_directory').value, request.map_url)
        except (OSError, ValueError) as error:
            self.get_logger().error(f'拒绝地图保存请求：{error}')
            response.result = False
            return response
        if not self._client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('内部Map Saver Service不可用')
            response.result = False
            return response
        forwarded = SaveMap.Request()
        forwarded.map_topic = request.map_topic or '/robot/map'
        forwarded.map_url = str(target)
        forwarded.image_format = request.image_format or 'pgm'
        forwarded.map_mode = request.map_mode or 'trinary'
        forwarded.free_thresh = request.free_thresh or 0.25
        forwarded.occupied_thresh = request.occupied_thresh or 0.65
        future = self._client.call_async(forwarded)
        deadline = time.monotonic() + 10.0
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.02)
        response.result = bool(future.done() and future.result() and future.result().result)
        if response.result:
            self.get_logger().info(f'地图已保存：{target}.yaml')
        else:
            self.get_logger().error('内部Map Saver保存失败或超时')
        return response


def main():
    rclpy.init()
    node = MapSaveGuard()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
