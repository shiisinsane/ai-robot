# 资源卡：image_transport 3.1.13

## 基本信息

- 资源类别：ROS 2图像传输抽象与派生传输插件；
- 来源：ROS Perception官方维护项目，<https://github.com/ros-perception/image_common>；
- 锁定版本：ROS包`3.1.13`，Debian包`3.1.13-1jammy.20260605.160640`；
- 许可证：BSD；
- 环境：Ubuntu 22.04、ROS 2 Humble；
- 审查日期：2026年8月4日。

## 使用与接口

- 保留`/robot/camera/color/image_raw`作为唯一基础公共图像接口；
- 压缩等传输是由`image_transport`提供的派生接口，不能替代原始图像；
- M3只验证标准RGB原始图像链，不引入目标识别或图像算法；
- `camera_info`由传感器桥接独立发布，不由`image_transport`生成；
- 当前未安装`camera_info_manager`，M3仿真路径不依赖它；若后续加载外部标定文件再审查。

## 验证与风险

- 本机`image_transport`及传输插件已安装，ROS 2能够发现软件包；
- ROS包元数据确认版本3.1.13、BSD许可证和上游仓库；
- 本次图像桥接实际得到`1×1`、`rgb8`、步长3的标准`Image`测试消息；
- M3-W4仍需在目标分辨率和帧率下测量带宽、时间戳与稳定性；
- 回退方法：禁用派生传输，仅保留标准原始图像Topic，不影响公共契约。

## 准入结论

- 状态：已准入；
- 范围：M3及后续ROS 2图像传输；
- 重新审查条件：图像Topic、编码、传输插件、带宽要求或包版本变化。
