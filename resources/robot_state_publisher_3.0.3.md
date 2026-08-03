# 资源卡：robot_state_publisher 3.0.3

## 基本信息

- 资源类别：机器人模型与TF状态发布；
- 来源：ROS官方发布，<https://github.com/ros/robot_state_publisher>；
- 锁定版本：ROS包`3.0.3`，Debian包`3.0.3-2jammy.20260605.161527`；
- 许可证：BSD-3-Clause；
- 环境：Ubuntu 22.04、ROS 2 Humble；
- 审查日期：2026年8月3日。

## 使用与接口

- 通过`robot_description`加载URDF，订阅`/robot/joint_states`；
- 固定关节发布到`/tf_static`，可动关节发布到`/tf`；
- 复用上游软件包和Launch配置，不修改第三方源码；
- 仿真与实体复用同一模型和Frame名称，只替换尺寸、外参与底层状态来源。

## 验证与风险

- `ros2 pkg xml robot_state_publisher`确认版本和BSD许可证；
- `ros2 pkg executables robot_state_publisher`确认节点可发现；
- 官方测试Xacro可展开为有效`robot` XML；
- M2-W3仍须验证项目模型的TF树、时间戳、唯一发布者和重复启动；
- 回退方法：锁定当前Debian包，升级失败时恢复该版本和原Launch配置。

## 准入结论

- 状态：已准入；
- 范围：M2机器人模型和状态发布；
- 重新审查条件：版本升级、Frame规则变化或仿真/实体模型分叉。
