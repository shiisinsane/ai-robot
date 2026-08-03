# 资源卡：gz_ros2_control 0.7.20

## 基本信息

- 资源类别：Gazebo Fortress与`ros2_control`集成插件；
- 来源：ros-controls官方项目，<https://github.com/ros-controls/gz_ros2_control>；
- 锁定版本：ROS包`0.7.20`，Debian包`0.7.20-1jammy.20260612.071115`；
- 许可证：Apache-2.0；
- 环境：Ubuntu 22.04、ROS 2 Humble、Gazebo Fortress 6.18.0；
- 审查日期：2026年8月3日。

## 使用与接口

- 通过`gz_ros2_control/GazeboSimSystem`把Gazebo关节连接到`ros2_control`；
- 使用URDF中的`ros2_control`和Gazebo插件配置，不修改上游源码；
- 公共Topic、TF和Frame继续遵守`m1.v1`，插件名称不暴露到公共接口；
- 只用于仿真实现，实体阶段替换为硬件接口或薄适配器。

## 验证与风险

- M1已验证Fortress官方无界面控制示例、控制器加载和关节状态；
- 本次确认插件描述包含`GazeboSimSystem`且共享库依赖完整；
- 官方Humble文档确认默认Gazebo组合为Fortress；
- 速度接口瞬时施加可能造成轮滑和里程计误差，M2-W6必须实测并记录；
- 回退方法：恢复锁定版本；仅在明确失败条件下临时回退Classic路线。

## 准入结论

- 状态：已准入；
- 范围：M2～M6 Gazebo Fortress控制集成；
- 重新审查条件：Gazebo版本、插件ABI、控制接口或上游支持状态变化。
