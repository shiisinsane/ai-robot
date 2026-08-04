# 资源卡：ros_gz 0.244.25

## 基本信息

- 资源类别：Gazebo Fortress与ROS 2 Humble桥接、仿真启动和图像转换组件；
- 来源：Gazebo官方项目，<https://github.com/gazebosim/ros_gz>；
- 锁定版本：ROS包`0.244.25`；Debian包为2026年6月构建的Jammy版本；
- 许可证：Apache-2.0；
- 关键组件：`ros_gz_bridge`、`ros_gz_image`、`ros_gz_sim`及官方demos；
- 审查日期：2026年8月4日。

## 使用与接口

- 使用`parameter_bridge`将Gazebo Transport消息转换为ROS 2标准消息；
- 雷达、相机、相机参数和IMU只采用Gazebo到ROS 2方向；
- 目标类型为`LaserScan`、`Image`、`CameraInfo`和`Imu`；
- 通过命名空间和显式重映射形成`/robot/scan`、`/robot/camera/color/*`和
  `/robot/imu/data`，公共名称不暴露`gz`、`ignition`或`sim`；
- 公共QoS继续使用M1的`sensor_stream`和`imu_stream`配置档。

## 验证与风险

- 本机ROS 2可发现所有关键组件，包版本和许可证元数据完整；
- 隔离ROS域和Gazebo Transport分区中，实际转换结果为：
  `LaserScan`保留Frame、角度、量程和数组；`Image`转换为`rgb8`；`CameraInfo`保留
  `640×480`和`plumb_bob`；`Imu`保留角速度和线加速度字段；
- 桥接能够创建双向端点，但项目传感器配置必须显式限制为Gazebo到ROS 2，避免测试或
  外部ROS节点反向写入仿真传感器Topic；
- 回退方法：恢复0.244.25；必要时采用同版本`ros_gz_image`处理图像，但公共Topic不变。

## 准入结论

- 状态：已准入；
- 范围：M3～M6 Fortress与ROS 2传感器消息桥接；
- 重新审查条件：消息映射、桥接方向、QoS默认值、包版本或公共接口变化。
