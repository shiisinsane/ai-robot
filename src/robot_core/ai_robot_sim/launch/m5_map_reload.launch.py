"""独立加载已保存的M5二维地图，用于W4重载验证。"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    map_server = Node(
        package='nav2_map_server', executable='map_server',
        namespace='robot', name='map_server', output='screen',
        parameters=[{'use_sim_time': False,
                     'yaml_filename': LaunchConfiguration('map')}],
        remappings=[('/map', '/robot/map'),
                    ('/map_metadata', '/robot/map_metadata')])
    lifecycle = Node(
        package='nav2_lifecycle_manager', executable='lifecycle_manager',
        namespace='robot', name='lifecycle_manager_map_reload', output='screen',
        parameters=[{'use_sim_time': False, 'autostart': True,
                     'node_names': ['map_server']}])
    return LaunchDescription([
        DeclareLaunchArgument('map', description='已保存地图YAML的绝对路径'),
        map_server,
        lifecycle,
    ])
