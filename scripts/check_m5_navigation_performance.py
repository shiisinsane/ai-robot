#!/usr/bin/env python3
"""测量M5-W9导航栈TF、传感器频率、实时因子和资源峰值。"""

import argparse
import os
import time

import psutil
import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage


class NavigationPerformanceCheck(Node):
    def __init__(self):
        super().__init__('m5_w9_navigation_performance_check')
        best_effort = QoSProfile(depth=200, reliability=ReliabilityPolicy.BEST_EFFORT)
        reliable = QoSProfile(depth=500, reliability=ReliabilityPolicy.RELIABLE)
        self.clock = []
        self.scan = []
        self.odom = []
        self.tf = {'map->odom': [], 'odom->base_link': []}
        self.create_subscription(
            Clock, '/clock', lambda msg: self.clock.append(
                (time.monotonic(), msg.clock.sec + msg.clock.nanosec / 1e9)),
            best_effort)
        self.create_subscription(
            LaserScan, '/robot/scan', lambda _: self.scan.append(time.monotonic()),
            best_effort)
        self.create_subscription(
            Odometry, '/robot/odom', lambda _: self.odom.append(time.monotonic()), 100)
        self.create_subscription(TFMessage, '/tf', self._tf, reliable)

    def _tf(self, message):
        now = time.monotonic()
        for transform in message.transforms:
            edge = f'{transform.header.frame_id}->{transform.child_frame_id}'
            if edge in self.tf:
                self.tf[edge].append(now)


def rate(samples):
    return ((len(samples) - 1) / (samples[-1] - samples[0])
            if len(samples) >= 2 and samples[-1] > samples[0] else 0.0)


def navigation_processes():
    tokens = ('gz sim', 'parameter_bridge', 'controller_manager', 'robot_state_publisher',
              'safety_supervisor.py', 'ekf_node', 'map_server', 'amcl',
              'planner_server', 'controller_server', 'behavior_server',
              'bt_navigator', 'navigate_action_adapter.py', 'nav_cmd_vel_keepalive.py')
    tokens = (*tokens, '/ai_robot_task_manager/lib/ai_robot_task_manager/task_manager')
    own = os.getpid()
    result = []
    for process in psutil.process_iter(['pid', 'cmdline']):
        try:
            command = ' '.join(process.info['cmdline'] or [])
            if process.info['pid'] != own and any(token in command for token in tokens):
                result.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=30.0)
    args = parser.parse_args()
    if args.duration < 30.0:
        print('M5-W9性能检查失败：正式测量窗口不得短于30秒')
        return 1
    rclpy.init()
    node = NavigationPerformanceCheck()
    try:
        processes = navigation_processes()
        if not processes:
            raise RuntimeError('未找到导航仿真进程')
        for process in processes:
            process.cpu_percent(None)
        warmup = time.monotonic() + 3.0
        while time.monotonic() < warmup:
            rclpy.spin_once(node, timeout_sec=0.03)
        node.clock.clear(); node.scan.clear(); node.odom.clear()
        for samples in node.tf.values():
            samples.clear()
        cpu_samples, rss_samples = [], []
        deadline = time.monotonic() + args.duration
        next_sample = time.monotonic()
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.02)
            if time.monotonic() >= next_sample:
                cpu = rss = 0.0
                for process in processes:
                    try:
                        cpu += process.cpu_percent(None)
                        rss += process.memory_info().rss / 1024 / 1024
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                cpu_samples.append(cpu); rss_samples.append(rss)
                next_sample += 1.0
        if len(node.clock) < 2:
            raise RuntimeError('仿真时钟样本不足')
        rtf = ((node.clock[-1][1] - node.clock[0][1]) /
               (node.clock[-1][0] - node.clock[0][0]))
        values = {
            '/robot/scan': rate(node.scan), '/robot/odom': rate(node.odom),
            'map->odom': rate(node.tf['map->odom']),
            'odom->base_link': rate(node.tf['odom->base_link']),
        }
        max_cpu = max(cpu_samples, default=0.0)
        max_rss = max(rss_samples, default=0.0)
        failures = []
        for name, measured, minimum in (
                ('/robot/scan', values['/robot/scan'] / rtf, 10.0),
                ('/robot/odom', values['/robot/odom'] / rtf, 20.0),
                ('map->odom', values['map->odom'] / rtf, 5.0),
                ('odom->base_link', values['odom->base_link'] / rtf, 20.0)):
            if measured < minimum * 0.95:
                failures.append(f'{name}频率{measured:.3f} Hz低于允许值{minimum * 0.95:.3f} Hz')
        if rtf < 0.5:
            failures.append(f'实时因子{rtf:.3f}低于0.5')
        if max_cpu > 500.0:
            failures.append(f'CPU峰值{max_cpu:.1f}%超过500%')
        if max_rss > 2560.0:
            failures.append(f'RSS峰值{max_rss:.1f} MiB超过2560 MiB')
        print('M5-W9导航性能测量结果')
        print(f'- 实时因子：{rtf:.3f}')
        print(f'- CPU峰值：{max_cpu:.1f}%；RSS峰值：{max_rss:.1f} MiB')
        for name, measured in values.items():
            print(f'- {name}：仿真时间频率{measured / rtf:.3f} Hz')
        if failures:
            print('- 未达标：' + '；'.join(failures))
            return 1
        print('- 结论：全部W2冻结性能门限通过')
        return 0
    except RuntimeError as error:
        print(f'M5-W9性能检查失败：{error}')
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
