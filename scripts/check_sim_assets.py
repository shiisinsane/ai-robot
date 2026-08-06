#!/usr/bin/env python3
"""离线检查M2-W4～W7仿真与安全控制资源，不启动Gazebo。"""

from pathlib import Path
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'src' / 'robot_core' / 'ai_robot_sim'


def main():
    required = [
        PACKAGE / 'package.xml',
        PACKAGE / 'CMakeLists.txt',
        PACKAGE / 'launch' / 'fortress.launch.py',
        PACKAGE / 'worlds' / 'm2_empty.sdf',
        PACKAGE / 'scripts' / 'cmd_vel_safety_filter.py',
        PACKAGE / 'scripts' / 'safety_supervisor.py',
        PACKAGE / 'scripts' / 'joint_state_qos_adapter.py',
        PACKAGE / 'launch' / 'integrated_bringup.launch.py',
        PACKAGE / 'worlds' / 'm4_integrated.sdf',
        PACKAGE / 'config' / 'controllers_m4.yaml',
        PACKAGE / 'config' / 'ekf_m4.yaml',
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        print('缺少W4资源：' + ', '.join(missing), file=sys.stderr)
        return 1

    world = ET.parse(PACKAGE / 'worlds' / 'm2_empty.sdf').getroot().find(
        "world[@name='m2_empty']")
    if world is None or world.find("model[@name='ground_plane']") is None:
        print('W4世界缺少m2_empty或ground_plane', file=sys.stderr)
        return 1

    launch_text = required[2].read_text()
    required_control = ('enable_control:=true', 'joint_state_broadcaster',
                        'diff_drive_base_controller')
    if not all(item in launch_text for item in required_control):
        print('W5控制器加载流程不完整', file=sys.stderr)
        return 1

    filter_text = (PACKAGE / 'scripts' / 'cmd_vel_safety_filter.py').read_text()
    if ('is_finite_twist' not in filter_text or
            "'/robot/controller_cmd_vel'" not in filter_text):
        print('W7速度命令安全过滤流程不完整', file=sys.stderr)
        return 1

    supervisor_text = (PACKAGE / 'scripts' / 'safety_supervisor.py').read_text()
    required_safety = ('/robot/cmd_vel', '/robot/safety_cmd_vel',
                       '/robot/safety/stop_active', '/robot/diagnostics',
                       '/robot/safety/clear_faults', 'command_timeout',
                       'odom_timeout', 'imu_timeout', 'scan_timeout',
                       'camera_timeout', 'invalid_command')
    if not all(item in supervisor_text for item in required_safety):
        print('M4-W7安全监督、诊断或故障锁存流程不完整', file=sys.stderr)
        return 1

    integrated = (PACKAGE / 'launch' / 'integrated_bringup.launch.py').read_text()
    required_m4 = ('enable_control:=true', 'enable_lidar:=true',
                   'enable_camera:=true', 'enable_imu:=true',
                   'controller_odom_topic:=internal/base_odom',
                   "('/robot/cmd_vel', '/robot/safety_cmd_vel')")
    if not all(item in integrated for item in required_m4):
        print('M4-W3统一Bringup边界不完整', file=sys.stderr)
        return 1

    m4_world = ET.parse(PACKAGE / 'worlds' / 'm4_integrated.sdf').getroot().find(
        "world[@name='m4_integrated']")
    m4_plugins = {plugin.attrib['filename'] for plugin in m4_world.findall('plugin')}
    if not {'ignition-gazebo-sensors-system', 'ignition-gazebo-imu-system'} <= m4_plugins:
        print('M4-W3统一世界缺少传感器系统', file=sys.stderr)
        return 1

    ekf = (PACKAGE / 'config' / 'ekf_m4.yaml').read_text()
    required_ekf = ('odom0: /robot/internal/base_odom', 'imu0: /robot/imu/data',
                    'publish_tf: true', 'world_frame: odom')
    if not all(item in ekf for item in required_ekf):
        print('M4-W4 EKF输入、输出或TF权威配置不完整', file=sys.stderr)
        return 1

    print('M2-W4～W7仿真与安全控制资源离线检查通过')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
