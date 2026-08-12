"""启动M6非AI任务管理器骨架。"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    namespace = LaunchConfiguration('robot_namespace')
    use_sim_time = LaunchConfiguration('use_sim_time')
    return LaunchDescription([
        DeclareLaunchArgument('robot_namespace', default_value='robot'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        Node(
            package='ai_robot_task_manager', executable='task_manager',
            name='task_manager', namespace=namespace, output='screen',
            parameters=[{'use_sim_time': use_sim_time}],
        ),
    ])
