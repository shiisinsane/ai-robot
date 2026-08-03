# 资源卡：diff_drive_controller 2.53.1

## 基本信息

- 资源类别：差速底盘控制器；
- 来源：ros-controls官方项目，<https://github.com/ros-controls/ros2_controllers>；
- 锁定版本：ROS包`2.53.1`，Debian包`2.53.1-1jammy.20260611.083619`；
- 许可证：Apache-2.0；
- 环境：Ubuntu 22.04、ROS 2 Humble；
- 审查日期：2026年8月3日。

## 使用与接口适配

- 输入机体线速度和角速度，输出左右轮速度命令；
- 基于轮反馈计算并发布里程计，可选择发布`odom → base_link`；
- M1公共输入为`/robot/cmd_vel`的`geometry_msgs/msg/Twist`，必须设置
  `use_stamped_vel: false`并将控制器私有`~/cmd_vel_unstamped`显式重映射到公共Topic；
- `~/odom`、`/tf`和`joint_states`必须适配M1名称、QoS和唯一发布责任；
- `cmd_vel_timeout`必须从上游默认`0.5 s`收紧为M1要求的`0.2 s`。

## 验证与安全

- 插件描述确认`diff_drive_controller/DiffDriveController`可发现，共享库依赖完整；
- 本机参数定义确认轮距、轮径、反馈、TF、发布频率、限速、超时和非时间戳命令模式可配置；
- 官方能力包含里程计、速度/加速度/加加速度限制和命令超时自动停车；
- M2-W5～W7必须验证实际Topic类型、重映射、生命周期、方向、限速和`0.2 s`停车；
- 禁止将控制器直接连接实体底盘；回退为锁定版本或自研薄仿真适配器。

## 准入结论

- 状态：已准入（附带M1接口适配约束）；
- 范围：M2 Gazebo差速底盘；
- 重新审查条件：公共`cmd_vel`类型、控制器输入Topic、里程计/TF责任或安全超时变化。
