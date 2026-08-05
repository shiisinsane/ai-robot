# robot_localization 3.5.4资源卡

## 基本信息

- 对象：M4局部状态估计；
- 上游仓库：`https://github.com/cra-ros-pkg/robot_localization`；
- 项目文档：`https://docs.ros.org/en/humble/p/robot_localization/`；
- Ubuntu 22.04/Humble候选包：`ros-humble-robot-localization`；
- 候选版本：`3.5.4-1jammy.20260605.164912`；
- 许可证：Apache License 2.0（以本机安装包`package.xml`为准）；
- 当前状态：已准入，本机版本和`ekf_node`可执行文件已验证。

## 采用范围

M4只采用`ekf_node`进行平面局部状态估计，输入M2底盘里程计和M3 IMU，输出项目命名空间
下的融合里程计，并按W2冻结结果决定`odom → base_link`唯一发布责任。不采用GPS、
`navsat_transform_node`、`map → odom`、SLAM或全局定位能力。

## 准入理由与验证要求

- 上游定位为非线性状态估计节点，符合ROS 2规划中的成熟资源优先原则；
- 官方示例支持`two_d_mode`、传感器超时、诊断和TF发布配置；
- W2必须解决原差速控制器与EKF重复发布`odom → base_link`的风险；
- W4必须验证静止、直行、转向、输入超时、协方差和时间戳；
- 失败回退为停用EKF并恢复M2已验收的底盘里程计与TF，不修改上游源码。
