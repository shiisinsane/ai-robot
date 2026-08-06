# Navigation2 1.1.20资源卡

## 基本信息

- 对象：M5地图服务、AMCL、全局规划、局部控制、行为树与恢复；
- 上游仓库：`https://github.com/ros-navigation/navigation2`；
- 项目文档：`https://docs.nav2.org/`；
- Ubuntu 22.04/Humble软件包：`ros-humble-navigation2`、`ros-humble-nav2-bringup`；
- 已安装版本：Navigation2 `1.1.20-1jammy.20260612.214117`，Nav2 Bringup
  `1.1.20-1jammy.20260612.221202`；
- 接口包：`ros-humble-nav2-msgs 1.1.20-1jammy.20260605.153126`；
- 许可证：逐包`package.xml`复核；主体为`Apache-2.0`，`nav2_amcl`为
  `LGPL-2.1-or-later`，`nav2_map_server`为`Apache-2.0`与`BSD-3-Clause`；
- 当前状态：已安装并通过M5-W2关键节点、接口和导航契约验证，准入M5仿真使用。

## 采用范围

M5采用Map Server、AMCL、Planner Server、Controller Server、BT Navigator、行为/恢复节点和
Lifecycle Manager，通过配置和薄Launch接入。公共任务接口保持M1冻结的
`NavigateToPose`、`FollowWaypoints`和`SaveMap`契约；所有速度输出必须进入M4安全监督器，不
允许Nav2直接连接控制器。

## 准入理由与验证要求

- ROS 2规划已指定Nav2和AMCL，Humble软件源提供同系列二进制包；
- W2已复核版本、许可证、关键节点、生命周期及`SaveMap`、`NavigateToPose`、
  `FollowWaypoints`接口类型；具体规划器和控制器插件在W6、W7随参数配置复核；
- W5验证地图定位、初始偏差收敛和`map → odom`责任切换；
- W6～W8分别验证全局规划、局部控制、静态/临时障碍、任务取消、不可达和恢复行为；
- W9验证性能、传感器超时及M4安全链不被绕过；
- 回退方法为停止Nav2生命周期节点，保留M4手动受监督运动和感知能力。

## 安全边界

- Nav2输出只能发布到`/robot/cmd_vel`公共受监督入口；
- 安全监督器停车状态优先于规划器和控制器命令；
- 地图缺失、定位失效、雷达/里程计/IMU超时或目标不可达时必须失败关闭；
- M5只在仿真中运行，不连接实体设备或AI Agent。
