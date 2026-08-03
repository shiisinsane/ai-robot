# 资源卡：ros2_controllers 2.53.1组件集

## 基本信息

- 资源类别：`ros2_control`标准控制器集合；
- 来源：ros-controls官方项目，<https://github.com/ros-controls/ros2_controllers>；
- 锁定版本：M2所用组件`2.53.1`；
- 许可证：Apache-2.0；
- 环境：Ubuntu 22.04、ROS 2 Humble；
- 审查日期：2026年8月3日。

## 使用与依赖策略

- M2只直接依赖`joint_state_broadcaster`和`diff_drive_controller`；
- 本机未安装`ros-humble-ros2-controllers`元包，但两个所需组件均已安装且可发现；
- 项目`package.xml`应声明实际组件，不用元包隐式引入未使用控制器；
- 控制器由`controller_manager`管理，启动顺序和生命周期必须由Launch测试验证。

## 验证与风险

- `joint_state_broadcaster 2.53.1`和`diff_drive_controller 2.53.1`元数据、许可证可解析；
- `controller_manager 2.54.0`已安装，补丁版本不同须在M2-W5执行组合集成测试；
- 不把安装元包本身作为准入条件，也不把未使用控制器纳入稳定接口；
- 回退方法：恢复组件锁定版本及控制器YAML。

## 准入结论

- 状态：已准入；
- 范围：M2直接使用的标准控制器组件；
- 重新审查条件：组件与`controller_manager`不兼容、生命周期行为变化或版本升级。
