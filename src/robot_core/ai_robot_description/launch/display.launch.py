"""启动M2机器人描述和robot_state_publisher，不启动Gazebo。"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    """构造只发布模型TF的LaunchDescription。"""
    share = Path(get_package_share_directory("ai_robot_description"))
    xacro_file = share / "urdf/ai_robot.urdf.xacro"
    default_config = share / "config/robot_model.yaml"
    model_config = LaunchConfiguration("model_config")

    robot_description = ParameterValue(
        Command(
            [
                "xacro ",
                str(xacro_file),
                " model_config:=",
                model_config,
            ]
        ),
        value_type=str,
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "model_config",
                default_value=str(default_config),
                description="机器人本体参数YAML",
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                namespace="robot",
                name="robot_state_publisher",
                output="screen",
                parameters=[
                    {
                        "robot_description": robot_description,
                        "use_sim_time": True,
                    }
                ],
                remappings=[
                    ("tf", "/tf"),
                    ("tf_static", "/tf_static"),
                ],
            ),
        ]
    )
