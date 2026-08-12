# rclpy 3.3.21资源卡

## 基本信息

- 对象：M6非AI任务管理器、任务Action服务端与下游能力Action客户端；
- 来源：ROS 2官方软件包`rclpy`；
- 上游仓库：`https://github.com/ros2/rclpy`；
- Ubuntu 22.04/Humble软件包：`ros-humble-rclpy`；
- 已安装版本：`3.3.21-1jammy.20260605.135319`；
- 配套Action状态包：`ros-humble-action-msgs 1.2.3-1jammy.20260605.130130`；
- 配套Nav2接口包：`ros-humble-nav2-msgs 1.1.20-1jammy.20260605.153126`；
- 许可证：Apache-2.0；
- 当前状态：已准入M6仿真任务管理薄封装。

## 使用目的与边界

M6使用`rclpy.action.ActionServer`暴露非AI任务接口，使用`ActionClient`调用M5冻结的导航能力。
任务管理器只负责目标校验、状态编排、反馈、取消、超时、结果汇总和故障传播，不实现路径规划、
运动控制、感知算法或安全控制。

不采用SMACH、外部工作流引擎或第二套Nav2行为树：M6场景为单机器人、短生命周期的确定性能力
编排，ROS 2 Action原语已覆盖异步反馈、取消和结果；新增框架会扩大依赖与状态语义。若M6后续
出现持久化、多机器人或复杂并行工作流需求，应重新进行资源审查。

## 接口与安全影响

- 新任务接口必须在W2通过自定义`robot_interfaces`包冻结，禁止用`std_msgs/String`传JSON；
- 下游仅调用公共`/robot/navigation/navigate_to_pose`等白名单接口；
- 不发布速度命令，不接触`/robot/safety_cmd_vel`或底盘内部控制接口；
- 安全停车、定位或传感器故障必须优先终止当前任务并返回稳定错误码；
- 所有超时使用ROS仿真时间语义或明确的看门狗策略，取消必须向下游传播；
- M6只在仿真中运行，不连接实体设备或AI Agent。

## 验证情况

2026年8月12日在Ubuntu 22.04、ROS 2 Humble本机环境完成最小导入验证：

- `rclpy.action.ActionServer`和`ActionClient`可导入；
- `action_msgs/msg/GoalStatus`可解析，`STATUS_SUCCEEDED=4`；
- `nav2_msgs/action/NavigateToPose`的Goal、Result和Feedback可解析；
- M5已完成公共导航Action的成功、失败、取消和故障注入黑盒验证。

回退方法为停止或不启动任务管理器，M5导航、感知和安全能力保持独立可用。版本升级、任务接口
破坏性变更、并行任务需求或迁移至实体运行时必须重新审查。
