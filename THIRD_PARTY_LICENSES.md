# 第三方资源与许可证说明

当前仓库不复制以下第三方源码，而是通过ROS 2二进制包依赖和配置复用：

后续引入第三方资源时，必须在本文件记录：

| 名称 | 来源 | 版本或提交 | 许可证 | 用途 | 修改情况 |
|---|---|---|---|---|---|
| `robot_state_publisher` | <https://github.com/ros/robot_state_publisher> | 3.0.3 | BSD-3-Clause | 机器人模型TF发布 | 未修改源码 |
| Xacro | <https://github.com/ros/xacro> | 2.1.1 | BSD | URDF宏展开 | 未修改源码 |
| `gz_ros2_control` | <https://github.com/ros-controls/gz_ros2_control> | 0.7.20 | Apache-2.0 | Fortress控制集成 | 未修改源码 |
| `ros2_controllers`组件 | <https://github.com/ros-controls/ros2_controllers> | 2.53.1 | Apache-2.0 | 关节状态和差速控制 | 未修改源码 |

准入要求：

- 确认许可证允许项目预期的使用和分发方式；
- 固定版本、发布标签或提交号；
- 保存官方来源和校验信息；
- 记录是否修改第三方代码；
- 不把许可证不明的代码、模型、地图或数据提交到仓库。
