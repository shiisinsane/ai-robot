#!/usr/bin/env python3
"""M4公共速度命令安全监督、故障锁存和诊断节点。"""

import math
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image, Imu, LaserScan
from std_msgs.msg import Bool
from std_srvs.srv import Trigger


STOP_TIMEOUTS = {'command': 0.2, 'base_odometry': 0.2, 'imu': 0.2, 'scan': 0.5}
WARN_TIMEOUTS = {'camera': 0.5}


def is_finite_twist(message):
    values = (
        message.linear.x, message.linear.y, message.linear.z,
        message.angular.x, message.angular.y, message.angular.z,
    )
    return all(math.isfinite(value) for value in values)


def is_zero_twist(message, tolerance=1e-9):
    values = (
        message.linear.x, message.linear.y, message.linear.z,
        message.angular.x, message.angular.y, message.angular.z,
    )
    return all(abs(value) <= tolerance for value in values)


class SafetySupervisor(Node):
    def __init__(self):
        super().__init__('safety_supervisor')
        sensor_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        latched_qos = QoSProfile(
            depth=1, reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self._last_seen = {name: None for name in (*STOP_TIMEOUTS, *WARN_TIMEOUTS)}
        self._last_command_zero = True
        self._latched_codes = set()
        self._output = self.create_publisher(Twist, '/robot/safety_cmd_vel', 10)
        self._stop_output = self.create_publisher(
            Bool, '/robot/safety/stop_active', latched_qos)
        self._diagnostics = self.create_publisher(
            DiagnosticArray, '/robot/diagnostics', 10)
        self.create_subscription(Twist, '/robot/cmd_vel', self._on_command, 10)
        self.create_subscription(
            Odometry, '/robot/internal/base_odom',
            lambda _: self._mark_seen('base_odometry'), 10)
        self.create_subscription(
            Imu, '/robot/imu/data', lambda _: self._mark_seen('imu'), sensor_qos)
        self.create_subscription(
            LaserScan, '/robot/scan', lambda _: self._mark_seen('scan'), sensor_qos)
        self.create_subscription(
            Image, '/robot/camera/color/image_raw',
            lambda _: self._mark_seen('camera'), sensor_qos)
        self.create_service(
            Trigger, '/robot/safety/clear_faults', self._clear_faults)
        self.create_timer(0.05, self._watchdog)
        self.create_timer(0.1, self._publish_diagnostics)

    def _mark_seen(self, name):
        self._last_seen[name] = time.monotonic()

    def _fresh(self, name, now):
        stamp = self._last_seen[name]
        timeout = STOP_TIMEOUTS.get(name, WARN_TIMEOUTS.get(name))
        return stamp is not None and now - stamp <= timeout

    def _stop_inputs_ready(self, now):
        return all(self._fresh(name, now) for name in STOP_TIMEOUTS)

    def _fault(self, code):
        if code not in self._latched_codes:
            self.get_logger().error(f'安全故障锁存：{code}')
        self._latched_codes.add(code)
        self._output.publish(Twist())

    def _on_command(self, message):
        self._last_seen['command'] = time.monotonic()
        if not is_finite_twist(message):
            self._last_command_zero = False
            self._fault('invalid_command')
            return
        self._last_command_zero = is_zero_twist(message)
        if not self._last_command_zero:
            now = time.monotonic()
            for name, code in (
                    ('base_odometry', 'odom_timeout'),
                    ('imu', 'imu_timeout'), ('scan', 'scan_timeout')):
                if not self._fresh(name, now):
                    self._fault(code)
        if not self._latched_codes and self._stop_inputs_ready(time.monotonic()):
            self._output.publish(message)
        else:
            self._output.publish(Twist())

    def _watchdog(self):
        now = time.monotonic()
        for name, code in (
                ('command', 'command_timeout'),
                ('base_odometry', 'odom_timeout'),
                ('imu', 'imu_timeout'),
                ('scan', 'scan_timeout')):
            if self._last_seen[name] is not None and not self._fresh(name, now):
                self._fault(code)
        stop_active = bool(self._latched_codes) or not self._stop_inputs_ready(now)
        if stop_active:
            self._output.publish(Twist())
        self._stop_output.publish(Bool(data=stop_active))

    def _clear_faults(self, _request, response):
        now = time.monotonic()
        if not self._last_command_zero:
            response.success = False
            response.message = '清除失败：速度命令必须为零'
        elif not self._stop_inputs_ready(now):
            response.success = False
            response.message = '清除失败：停车级输入尚未全部恢复'
        else:
            self._latched_codes.clear()
            response.success = True
            response.message = '安全故障已清除'
        return response

    def _publish_diagnostics(self):
        now = time.monotonic()
        stale_stop = [name for name in STOP_TIMEOUTS if not self._fresh(name, now)]
        stale_warn = [name for name in WARN_TIMEOUTS if not self._fresh(name, now)]
        codes = sorted(self._latched_codes)
        if codes or stale_stop:
            level = DiagnosticStatus.ERROR
            code = ','.join(codes or [f'{name}_not_ready' for name in stale_stop])
            message = '安全停车生效'
        elif stale_warn:
            level = DiagnosticStatus.WARN
            code = 'camera_timeout'
            message = '相机数据超时，不触发停车'
        else:
            level = DiagnosticStatus.OK
            code = 'ok'
            message = '安全监督正常'
        status = DiagnosticStatus(
            level=level, name='safety_supervisor', message=message,
            hardware_id='simulation')
        values = {
            'component': 'safety_supervisor', 'code': code, 'message': message,
            'stamp': f'{time.time():.6f}',
            'latched': str(bool(self._latched_codes)).lower(),
        }
        status.values = [KeyValue(key=key, value=value) for key, value in values.items()]
        array = DiagnosticArray()
        array.header.stamp = self.get_clock().now().to_msg()
        array.status = [status]
        self._diagnostics.publish(array)


def main(args=None):
    rclpy.init(args=args)
    node = SafetySupervisor()
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
