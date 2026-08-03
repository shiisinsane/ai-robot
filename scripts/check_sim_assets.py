#!/usr/bin/env python3
"""离线检查M2-W4仿真资源，不启动Gazebo。"""

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
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        print('缺少W4资源：' + ', '.join(missing), file=sys.stderr)
        return 1

    world = ET.parse(required[-1]).getroot().find("world[@name='m2_empty']")
    if world is None or world.find("model[@name='ground_plane']") is None:
        print('W4世界缺少m2_empty或ground_plane', file=sys.stderr)
        return 1

    launch_text = required[2].read_text()
    forbidden = ('gz_ros2_control', '/robot/cmd_vel')
    if any(item in launch_text for item in forbidden):
        print('W4加载流程越界包含控制或运动接口', file=sys.stderr)
        return 1

    print('M2-W4仿真资源离线检查通过')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
