# 资源卡：Ignition Sensors 6.9.0

## 基本信息

- 资源类别：Gazebo Fortress传感器库与系统插件；
- 来源：Gazebo官方项目，<https://github.com/gazebosim/gz-sensors>；
- 锁定版本：`libignition-sensors6`及camera、gpu-lidar、imu组件`6.9.0-1~jammy`；
- 许可证：Apache-2.0，文档中的特定材料为CC-BY-4.0；
- 环境：Ubuntu 22.04、ROS 2 Humble、Gazebo Fortress 6.18.0；
- 审查日期：2026年8月4日。

## 使用与接口

- 使用Fortress原生GPU Lidar、Camera和IMU传感器，不修改上游源码；
- Gazebo Transport原始消息分别为`ignition.msgs.LaserScan`、`Image`、`CameraInfo`和`IMU`；
- 通过`ros_gz`桥接为M1冻结的ROS 2标准Topic和`sensor_msgs`类型；
- 传感器安装位姿和Frame由项目Xacro管理，插件不拥有公共接口命名；
- 实体阶段替换为厂商驱动或薄适配器，上层公共接口不变。

## 验证与风险

- 本机确认Sensors 6.9.0的camera、gpu-lidar和imu组件及Fortress Sensors/IMU系统插件存在；
- 官方`ros_gz_sim_demos`提供GPU Lidar、Camera、CameraInfo和IMU示例；
- 四类Gazebo消息到ROS 2标准消息的实际转换已通过；
- 用户已确认官方GPU Lidar示例的“游乐场”世界可在Gazebo GUI中显示；但OGRE2服务端
  无界面渲染曾因NVIDIA/EGL上下文创建失败而退出，W3/W4仍须验证传感器数据和无界面回归；
- IMU原始Gazebo消息不直接携带ROS协方差，M3-W2必须冻结协方差表达和适配责任；
- 回退方法：恢复锁定的Fortress/Sensors版本；若GPU Lidar持续受渲染影响，可评估同版本
  CPU Lidar，但不得更改`/robot/scan`公共契约。

## 准入结论

- 状态：已准入；
- 范围：M3～M6仿真雷达、RGB相机和IMU实现；
- 不代表传感器数据语义、频率、噪声或项目场景已经验收；这些分别由M3-W2～W5完成；
- 重新审查条件：Fortress、Sensors、渲染后端、传感器类型或插件ABI变化。
