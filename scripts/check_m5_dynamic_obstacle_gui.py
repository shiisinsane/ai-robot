#!/usr/bin/env python3
"""自动执行W8行驶中投入障碍并保持到机器人完成几何绕行的GUI复验。"""

import argparse
import math
import subprocess
import time

import rclpy
from action_msgs.msg import GoalStatus
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from geometry_msgs.msg import Twist
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener


PARKED_POSE = (8.0, 8.0, 0.45)


def yaw_of(quaternion):
    return math.atan2(
        2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1.0 - 2.0 * (quaternion.y * quaternion.y + quaternion.z * quaternion.z))


def angle_error(left, right):
    return math.atan2(math.sin(left - right), math.cos(left - right))


def set_obstacle_pose(world, x, y, z=0.45):
    """通过Gazebo UserCommands确定性设置临时障碍世界位姿。"""
    command = [
        'ign', 'service', '-s', f'/world/{world}/set_pose',
        '--reqtype', 'ignition.msgs.Pose',
        '--reptype', 'ignition.msgs.Boolean', '--timeout', '3000',
        '--req', (f'name: "temporary_obstacle", '
                  f'position: {{x: {x:.6f}, y: {y:.6f}, z: {z:.6f}}}'),
    ]
    result = subprocess.run(
        command, check=False, capture_output=True, text=True, timeout=5.0)
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0 or 'data: true' not in output.lower():
        raise RuntimeError(
            f'设置temporary_obstacle位姿失败（返回码{result.returncode}）：{output}')


class DynamicObstacleCheck(Node):
    def __init__(self):
        super().__init__('m5_w8_dynamic_obstacle_gui_check')
        self.client = ActionClient(
            self, NavigateToPose, '/robot/navigation/navigate_to_pose')
        self.zero = self.create_publisher(Twist, '/robot/cmd_vel', 10)
        self.clear = self.create_client(Trigger, '/robot/safety/clear_faults')
        self.commands = []
        self.safety = []
        self.feedback = []
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)
        self.create_subscription(Twist, '/robot/cmd_vel', self._command, 50)
        self.create_subscription(
            DiagnosticArray, '/robot/diagnostics', self._diagnostics, 50)

    def _command(self, message):
        self.commands.append((time.monotonic(), message.linear.x,
                              message.angular.z))

    def _diagnostics(self, message):
        for status in message.status:
            if status.name != 'safety_supervisor':
                continue
            values = {item.key: item.value for item in status.values}
            self.safety.append((time.monotonic(), status.level,
                                values.get('code', ''),
                                values.get('latched', '')))

    def pose(self):
        transform = self.buffer.lookup_transform(
            'map', 'base_link', rclpy.time.Time())
        return (transform.transform.translation.x,
                transform.transform.translation.y,
                yaw_of(transform.transform.rotation))

    def spin_until(self, predicate, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not predicate():
            rclpy.spin_once(self, timeout_sec=0.04)
        return predicate()

    def prepare(self):
        if not self.client.wait_for_server(timeout_sec=30.0):
            raise RuntimeError('公共导航Action不可用')
        if not self.clear.wait_for_service(timeout_sec=5.0):
            raise RuntimeError('安全清除Service不可用')
        if not self.spin_until(
                lambda: self.buffer.can_transform(
                    'map', 'base_link', rclpy.time.Time()), 10.0):
            raise RuntimeError('map到base_link TF不可用')
        for _ in range(3):
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                self.zero.publish(Twist())
                rclpy.spin_once(self, timeout_sec=0.05)
            future = self.clear.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
            if (future.done() and future.result() is not None and
                    future.result().success):
                return
        raise RuntimeError('安全故障清除失败')


def make_goal(x, y, yaw):
    goal = NavigateToPose.Goal()
    goal.pose.header.frame_id = 'map'
    goal.pose.pose.position.x = x
    goal.pose.pose.position.y = y
    goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
    goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
    return goal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--goal-x', type=float, default=2.0)
    parser.add_argument('--goal-y', type=float, default=0.0)
    parser.add_argument('--goal-yaw', type=float, default=0.0)
    parser.add_argument('--world', default='m5_slam')
    parser.add_argument('--movement-before-injection', type=float, default=0.15)
    parser.add_argument('--obstacle-ahead', type=float, default=1.10)
    parser.add_argument('--bypass-timeout', type=float, default=60.0)
    parser.add_argument('--minimum-lateral-clearance', type=float, default=0.50)
    parser.add_argument('--pass-margin', type=float, default=0.45)
    parser.add_argument('--motion-timeout', type=float, default=20.0)
    parser.add_argument('--navigation-timeout', type=float, default=90.0)
    parser.add_argument('--position-tolerance', type=float, default=0.15)
    args = parser.parse_args()
    if args.bypass_timeout < 20.0:
        print('M5-W8动态障碍GUI检查失败：绕行等待门限不得短于20秒')
        return 1
    if args.minimum_lateral_clearance < 0.48:
        print('M5-W8动态障碍GUI检查失败：横向绕行门限不得低于车体与障碍半宽之和0.48 m')
        return 1

    rclpy.init()
    node = DynamicObstacleCheck()
    obstacle_parked = False
    handle = None
    try:
        set_obstacle_pose(args.world, *PARKED_POSE)
        obstacle_parked = True
        node.prepare()
        start = node.pose()
        goal_distance = math.hypot(args.goal_x - start[0], args.goal_y - start[1])
        if goal_distance < args.movement_before_injection + args.obstacle_ahead + 0.55:
            raise RuntimeError(
                f'起点到目标仅{goal_distance:.3f} m，无法保证动态障碍位于二者之间')
        print(f'- 起点：({start[0]:.3f}, {start[1]:.3f})，目标：'
              f'({args.goal_x:.3f}, {args.goal_y:.3f})，距离{goal_distance:.3f} m')

        send = node.client.send_goal_async(
            make_goal(args.goal_x, args.goal_y, args.goal_yaw),
            feedback_callback=lambda message: node.feedback.append(message.feedback))
        rclpy.spin_until_future_complete(node, send, timeout_sec=5.0)
        if not send.done() or send.result() is None or not send.result().accepted:
            raise RuntimeError('公共导航目标未接受')
        handle = send.result()
        result = handle.get_result_async()

        def moved_enough():
            try:
                current = node.pose()
            except Exception:
                return False
            displacement = math.hypot(current[0] - start[0], current[1] - start[1])
            moving = any(abs(x) > 0.01 or abs(z) > 0.01
                         for _, x, z in node.commands[-20:])
            return displacement >= args.movement_before_injection and moving

        if not node.spin_until(moved_enough, args.motion_timeout):
            raise RuntimeError('机器人未在门限内实际运动到障碍投入条件')
        current = node.pose()
        remaining_x = args.goal_x - current[0]
        remaining_y = args.goal_y - current[1]
        remaining = math.hypot(remaining_x, remaining_y)
        if remaining <= args.obstacle_ahead + 0.55:
            raise RuntimeError('投入时机器人距目标过近，无法保证障碍严格位于中间')
        unit_x, unit_y = remaining_x / remaining, remaining_y / remaining
        obstacle_x = current[0] + args.obstacle_ahead * unit_x
        obstacle_y = current[1] + args.obstacle_ahead * unit_y

        # 投影必须严格落在机器人到目标的开区间内，横向误差由构造保证为零。
        projection = ((obstacle_x - current[0]) * unit_x +
                      (obstacle_y - current[1]) * unit_y)
        lateral = abs((obstacle_x - current[0]) * unit_y -
                      (obstacle_y - current[1]) * unit_x)
        if not (0.55 < projection < remaining - 0.55) or lateral > 0.02:
            raise RuntimeError(
                f'障碍几何校验失败：投影{projection:.3f} m，横向{lateral:.3f} m')

        injected_at = time.monotonic()
        set_obstacle_pose(args.world, obstacle_x, obstacle_y)
        obstacle_parked = False
        print(f'- 已自动投入障碍：机器人({current[0]:.3f}, {current[1]:.3f})，'
              f'障碍({obstacle_x:.3f}, {obstacle_y:.3f})，'
              f'目标({args.goal_x:.3f}, {args.goal_y:.3f})')
        print(f'- 几何证据：障碍沿机器人到目标方向前方{projection:.3f} m，'
              f'横向偏差{lateral:.3f} m，严格位于二者之间')

        print('- 障碍将保持原位，只有机器人产生足够横向净距并越过障碍后方安全平面才会移除')
        bypass_deadline = time.monotonic() + args.bypass_timeout
        max_lateral = 0.0
        max_longitudinal = 0.0
        bypass_pose = None
        while time.monotonic() < bypass_deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            robot = node.pose()
            relative_x = robot[0] - current[0]
            relative_y = robot[1] - current[1]
            longitudinal = relative_x * unit_x + relative_y * unit_y
            robot_lateral = abs(relative_x * unit_y - relative_y * unit_x)
            max_longitudinal = max(max_longitudinal, longitudinal)
            max_lateral = max(max_lateral, robot_lateral)
            passed = longitudinal >= projection + args.pass_margin
            cleared_side = max_lateral >= args.minimum_lateral_clearance
            if passed and cleared_side:
                bypass_pose = robot
                break
            if result.done():
                raise RuntimeError(
                    'Action在取得绕行几何证据前结束：'
                    f'最大纵向{max_longitudinal:.3f} m，最大横向{max_lateral:.3f} m')
        if bypass_pose is None:
            raise RuntimeError(
                f'障碍保持{args.bypass_timeout:.1f} s仍未完成有效绕行：'
                f'最大纵向{max_longitudinal:.3f} m（要求至少'
                f'{projection + args.pass_margin:.3f} m），最大横向'
                f'{max_lateral:.3f} m（要求至少'
                f'{args.minimum_lateral_clearance:.3f} m）')
        bad_safety = [item for item in node.safety
                      if item[0] >= injected_at and
                      (item[1] == DiagnosticStatus.ERROR or item[3] == 'true')]
        if bad_safety:
            raise RuntimeError(f'障碍保持期间安全诊断异常：{bad_safety[-1][2]}')

        set_obstacle_pose(args.world, *PARKED_POSE)
        obstacle_parked = True
        print(f'- 绕行证据成立：机器人({bypass_pose[0]:.3f}, '
              f'{bypass_pose[1]:.3f})已越过障碍，最大纵向'
              f'{max_longitudinal:.3f} m、最大横向{max_lateral:.3f} m')
        print('- 仅在上述证据成立后，障碍才自动移回场外；继续等待最终到点')
        rclpy.spin_until_future_complete(node, result, timeout_sec=args.navigation_timeout)
        if not result.done() or result.result() is None:
            raise RuntimeError('移除障碍后导航未在门限内结束')
        if result.result().status != GoalStatus.STATUS_SUCCEEDED:
            raise RuntimeError(
                f'移除障碍后Action状态不是SUCCEEDED：{result.result().status}')
        final = node.pose()
        position_error = math.hypot(final[0] - args.goal_x, final[1] - args.goal_y)
        heading_error = abs(angle_error(final[2], args.goal_yaw))
        if position_error > args.position_tolerance:
            raise RuntimeError(f'终点位置误差{position_error:.3f} m超限')
        print('M5-W8动态障碍GUI检查通过')
        print('- 投入时障碍经实时TF计算并验证严格位于机器人与目标之间')
        print(f'- 障碍保持原位直至几何绕行完成：最大横向'
              f'{max_lateral:.3f} m，越障纵向{max_longitudinal:.3f} m')
        print(f'- 障碍移除后公共Action返回SUCCEEDED，终点误差：'
              f'位置{position_error:.3f} m，角度{heading_error:.3f} rad')
        return 0
    except (RuntimeError, subprocess.SubprocessError) as error:
        print(f'M5-W8动态障碍GUI检查失败：{error}')
        return 1
    finally:
        if handle is not None:
            try:
                cancel = handle.cancel_goal_async()
                rclpy.spin_until_future_complete(node, cancel, timeout_sec=2.0)
            except Exception as error:
                print(f'警告：测试收尾取消导航失败：{error}')
        if not obstacle_parked:
            try:
                set_obstacle_pose(args.world, *PARKED_POSE)
            except Exception as error:
                print(f'警告：临时障碍自动回收失败：{error}')
        node.zero.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
