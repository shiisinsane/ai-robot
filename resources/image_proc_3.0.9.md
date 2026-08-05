# image_proc 3.0.9资源卡

## 基本信息

- 对象：M4 RGB图像基础处理；
- 上游仓库：`https://github.com/ros-perception/image_pipeline`；
- 项目文档：`https://docs.ros.org/en/humble/p/image_proc/`；
- Ubuntu 22.04/Humble候选包：`ros-humble-image-proc`；
- 候选版本：`3.0.9-1jammy.20260606.044028`；
- 许可证：BSD风格许可证，以候选二进制包和上游`LICENSE`为准；
- 当前状态：已准入，本机版本、BSD许可证和`rectify_node`等可执行文件已验证。

## 采用范围

M4只建立RGB图像的基础处理链，优先验证去畸变/校正后的标准图像、`CameraInfo`、QoS、
Frame、时间戳和处理延迟。不进入目标检测、人员识别、深度处理、视觉里程计或AI视觉。

## 准入理由与验证要求

- 上游定位为相机驱动与高层视觉之间的标准图像处理流水线；
- 复用M3已验收的RGB图像和有效内参，不修改第三方源码；
- W2需冻结原始与处理后Topic、QoS和命名，避免改变M1公共原始图像接口；
- W6需验证输入输出时间戳、Frame、分辨率、编码和延迟；
- 若零畸变仿真相机使校正结果等同输入，仍须证明处理节点真实订阅和发布，不能只检查Topic存在。
