#!/usr/bin/env python3
"""在30秒窗口测量M4整机性能、Topic、QoS、时间戳和TF完整性。"""

import argparse
import os
import time

import psutil
import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import CameraInfo, Image, Imu, JointState, LaserScan
from std_msgs.msg import Bool
from tf2_msgs.msg import TFMessage


TOPICS = {
    '/robot/odom': (Odometry, 20.0, 'reliable', 'volatile'),
    '/robot/joint_states': (JointState, 20.0, 'reliable', 'volatile'),
    '/robot/scan': (LaserScan, 10.0, 'best_effort', 'volatile'),
    '/robot/imu/data': (Imu, 50.0, 'best_effort', 'volatile'),
    '/robot/camera/color/image_raw': (Image, 15.0, 'best_effort', 'volatile'),
    '/robot/camera/color/camera_info': (CameraInfo, 15.0, 'best_effort', 'volatile'),
    '/robot/camera/color/image_rect': (Image, None, 'best_effort', 'volatile'),
    '/robot/diagnostics': (DiagnosticArray, 1.0, 'reliable', 'volatile'),
    '/robot/safety/stop_active': (Bool, 10.0, 'reliable', 'transient_local'),
}


def _stamp_seconds(message):
    header = getattr(message, 'header', None)
    if header is None:
        return None
    return header.stamp.sec + header.stamp.nanosec / 1e9


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


class PerformanceCheck(Node):
    def __init__(self):
        super().__init__('m4_w8_performance_check')
        self.samples = {topic: [] for topic in TOPICS}
        self.clock = []
        self.tf_edges = set()
        sensor_qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT)
        reliable_qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE)
        latched_qos = QoSProfile(
            depth=100, reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL)
        for topic, (message_type, _, reliability, durability) in TOPICS.items():
            qos = sensor_qos if reliability == 'best_effort' else reliable_qos
            if durability == 'transient_local':
                qos = latched_qos
            self.create_subscription(
                message_type, topic,
                lambda message, name=topic: self.samples[name].append(
                    (time.monotonic(), _stamp_seconds(message))), qos)
        self.create_subscription(
            Clock, '/clock',
            lambda message: self.clock.append((
                time.monotonic(), message.clock.sec + message.clock.nanosec / 1e9)),
            sensor_qos)
        self.create_subscription(TFMessage, '/tf', self._on_tf, reliable_qos)
        self.create_subscription(TFMessage, '/tf_static', self._on_tf, latched_qos)

    def _on_tf(self, message):
        for transform in message.transforms:
            self.tf_edges.add((transform.header.frame_id, transform.child_frame_id))


def _launch_tree():
    own_pid = os.getpid()
    expected_domain = os.environ.get('ROS_DOMAIN_ID', '0')
    candidates = []
    for process in psutil.process_iter(['pid', 'cmdline']):
        try:
            arguments = process.info['cmdline'] or []
            command = ' '.join(arguments)
            if ('ros2 launch ai_robot_sim integrated_bringup.launch.py' in command
                    and any(argument.endswith('/ros2') for argument in arguments)
                    and process.environ().get('ROS_DOMAIN_ID', '0') == expected_domain
                    and process.info['pid'] != own_pid):
                candidates.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if len(candidates) != 1:
        details = []
        for process in candidates:
            try:
                details.append(f'{process.pid}:{process.name()}:{process.cmdline()}')
            except psutil.Error:
                pass
        raise RuntimeError(
            f'必须且只能有一个统一Bringup进程，实际{len(candidates)}个：{details}')
    root = candidates[0]
    processes = [root, *root.children(recursive=True)]
    for process in processes:
        try:
            process.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return root, processes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=float, default=30.0)
    args = parser.parse_args()
    _require(args.duration >= 30.0, '正式性能窗口不得短于30秒')
    rclpy.init()
    node = PerformanceCheck()
    try:
        failures = []
        root, processes = _launch_tree()
        warmup = time.monotonic() + 5.0
        while time.monotonic() < warmup:
            rclpy.spin_once(node, timeout_sec=0.05)
        for values in node.samples.values():
            values.clear()
        node.clock.clear()
        cpu_samples = []
        rss_samples = []
        end = time.monotonic() + args.duration
        next_resource = time.monotonic()
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.02)
            if time.monotonic() >= next_resource:
                live = processes
                cpu = rss = 0.0
                for process in live:
                    try:
                        cpu += process.cpu_percent(None)
                        rss += process.memory_info().rss / 1024 / 1024
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                cpu_samples.append(cpu)
                rss_samples.append(rss)
                next_resource += 1.0

        _require(len(node.clock) >= 2, '时钟样本不足')
        wall_delta = node.clock[-1][0] - node.clock[0][0]
        sim_delta = node.clock[-1][1] - node.clock[0][1]
        rtf = sim_delta / wall_delta
        if rtf < 0.5:
            failures.append(f'实时因子不足：{rtf:.3f} < 0.5')
        max_cpu = max(cpu_samples, default=0.0)
        max_rss = max(rss_samples, default=0.0)
        if max_cpu > 400.0:
            failures.append(f'CPU峰值超限：{max_cpu:.1f}%')
        if max_rss > 2048.0:
            failures.append(f'RSS峰值超限：{max_rss:.1f} MiB')

        results = {}
        for topic, (_, minimum, reliability, durability) in TOPICS.items():
            values = node.samples[topic]
            _require(len(values) >= 2, f'{topic}消息不足')
            wall_rate = (len(values) - 1) / (values[-1][0] - values[0][0])
            stamps = [stamp for _, stamp in values if stamp is not None]
            sim_rate = None
            if len(stamps) >= 2:
                _require(all(right > left for left, right in zip(stamps, stamps[1:])),
                         f'{topic}时间戳未严格递增')
                sim_rate = (len(stamps) - 1) / (stamps[-1] - stamps[0])
            measured = sim_rate if sim_rate is not None else wall_rate / rtf
            if minimum is not None:
                if measured < minimum * 0.95:
                    failures.append(
                        f'{topic}频率不足：{measured:.3f} < {minimum * 0.95:.3f} Hz')
            publishers = node.get_publishers_info_by_topic(topic)
            _require(publishers, f'{topic}没有发布者')
            for publisher in publishers:
                qos = publisher.qos_profile
                expected_reliability = (
                    ReliabilityPolicy.RELIABLE if reliability == 'reliable'
                    else ReliabilityPolicy.BEST_EFFORT)
                expected_durability = (
                    DurabilityPolicy.TRANSIENT_LOCAL
                    if durability == 'transient_local' else DurabilityPolicy.VOLATILE)
                if qos.reliability != expected_reliability:
                    failures.append(f'{topic}发布QoS可靠性错误：{qos.reliability}')
                if qos.durability != expected_durability:
                    failures.append(f'{topic}发布QoS持久性错误：{qos.durability}')
            results[topic] = (wall_rate, sim_rate, len(publishers))

        required_edges = {
            ('odom', 'base_link'), ('base_link', 'laser_link'),
            ('base_link', 'camera_link'), ('camera_link', 'camera_color_optical_frame'),
            ('base_link', 'imu_link'),
        }
        if not required_edges <= node.tf_edges:
            failures.append(f'TF边缺失：{sorted(required_edges - node.tf_edges)}')
        tf_publishers = node.get_publishers_info_by_topic('/tf')
        authorities = [item.node_name for item in tf_publishers]
        if authorities.count('state_estimator') != 1:
            failures.append(f'odom动态TF权威异常：{authorities}')

        print('M4-W8性能与完整性测量结果')
        print(f'- 实时因子：{rtf:.3f}')
        print(f'- CPU峰值：{max_cpu:.1f}%')
        print(f'- RSS峰值：{max_rss:.1f} MiB')
        for topic, (wall_rate, sim_rate, publishers) in results.items():
            sim_text = '-' if sim_rate is None else f'{sim_rate:.3f}'
            print(f'- {topic}: 墙钟{wall_rate:.3f} Hz，仿真时间{sim_text} Hz，发布者{publishers}')
        print(f'- TF动态发布者：{authorities}')
        if failures:
            print('- 未达标项：')
            for failure in failures:
                print(f'  - {failure}')
            raise RuntimeError(f'W8共有{len(failures)}项未达标')
        print('- 结论：全部冻结指标通过')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
