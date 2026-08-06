# slam_toolbox 2.6.10资源卡

## 基本信息

- 对象：M5二维SLAM、地图序列化与定位模式；
- 上游仓库：`https://github.com/SteveMacenski/slam_toolbox`；
- 项目文档：`https://docs.ros.org/en/humble/p/slam_toolbox/`；
- Ubuntu 22.04/Humble软件包：`ros-humble-slam-toolbox`；
- 已安装版本：`2.6.10-1jammy.20260612.214828`；
- 许可证：已按安装包`package.xml`复核为`LGPL`；
- 当前状态：已安装并通过M5-W2最小依赖、可执行文件和契约验证，准入M5仿真使用。

## 采用范围

M5只采用二维激光建图、地图序列化/反序列化和必要的定位模式。输入沿用M4冻结的
`/robot/scan`、`odom → base_link`和仿真时间，输出`map → odom`及地图数据。不修改上游源码，
不在本阶段接入三维SLAM、视觉SLAM、实体雷达或云端地图服务。

## 准入理由与验证要求

- ROS 2规划已指定`slam_toolbox`作为SLAM候选成熟资源；
- 支持Humble、生命周期节点、同步/异步建图和地图序列化；
- W2已复核版本、许可证、异步/同步建图与定位可执行文件，并冻结Service、QoS、生命周期和参数边界；
- W3必须验证闭环路线建图、地图连续性和`map → odom`唯一权威；
- W4必须验证地图保存、序列化、重载及不安全路径拒绝；
- 回退方法为停用SLAM Launch并恢复M4的纯`odom`局部坐标系统。

## 安全边界

- SLAM不得直接发布底盘速度或绕过安全监督器；
- 建图质量下降不得自动扩大机器人运动权限；
- 雷达、里程计或TF超时时必须由M4安全链保持停车；
- 未完成地图和定位验收前不得启动自主导航任务。
