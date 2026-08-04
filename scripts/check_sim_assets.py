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

    print('M2-W4～W7仿真与安全控制资源离线检查通过')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
