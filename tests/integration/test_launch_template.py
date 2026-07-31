"""Launch测试模板：启动节点并按计划安全停止。"""

import launch
import launch_ros.actions
from launch.actions import EmitEvent, TimerAction
from launch.events import Shutdown


def test_launch_starts_and_stops_ros_node():
    service = launch.LaunchService(argv=[], noninteractive=True)
    node = launch_ros.actions.Node(
        package="ai_robot_py_demo",
        executable="status_publisher",
        name="w6_launch_test_node",
        output="screen",
    )
    stop = TimerAction(
        period=0.5,
        actions=[EmitEvent(event=Shutdown(reason="W6 Launch模板完成"))],
    )
    service.include_launch_description(launch.LaunchDescription([node, stop]))

    assert service.run() == 0
