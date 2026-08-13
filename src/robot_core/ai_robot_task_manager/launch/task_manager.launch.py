"""启动M6非AI任务管理器骨架。"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    namespace = LaunchConfiguration('robot_namespace')
    use_sim_time = LaunchConfiguration('use_sim_time')
    sensing_wait = LaunchConfiguration('sensing_wait_sec')
    freshness = LaunchConfiguration('sensor_freshness_sec')
    cancel_propagation = LaunchConfiguration('cancel_propagation_sec')
    return LaunchDescription([
        DeclareLaunchArgument('robot_namespace', default_value='robot'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('sensing_wait_sec', default_value='5.0'),
        DeclareLaunchArgument('sensor_freshness_sec', default_value='0.5'),
        DeclareLaunchArgument('cancel_propagation_sec', default_value='2.0'),
        Node(
            package='ai_robot_task_manager', executable='task_manager',
            name='task_manager', namespace=namespace, output='screen',
            parameters=[{'use_sim_time': use_sim_time,
                         'sensing_wait_sec': sensing_wait,
                         'sensor_freshness_sec': freshness,
                         'cancel_propagation_sec': cancel_propagation}],
        ),
    ])
