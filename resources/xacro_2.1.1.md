# 资源卡：Xacro 2.1.1

## 基本信息

- 资源类别：URDF宏与模型生成工具；
- 来源：ROS官方发布，<https://github.com/ros/xacro>；
- 锁定版本：ROS包`2.1.1`，Debian包`2.1.1-1jammy.20260304.195513`；
- 许可证：BSD；
- 环境：Ubuntu 22.04、ROS 2 Humble；
- 审查日期：2026年8月3日。

## 使用与边界

- 用于拆分几何、惯量、关节、Gazebo和`ros2_control`模型片段；
- 模型参数保持唯一来源，禁止在URDF、控制器YAML和测试中重复硬编码；
- 生成标准URDF，不把Xacro宏名暴露为ROS 2公共接口；
- 不引入项目外模型代码或未经审查的网格资源。

## 验证与风险

- `ros2 pkg xml xacro`确认版本、许可证和上游地址；
- 使用官方`test-desc.urdf.xacro`展开并通过XML解析；
- M2-W3须增加项目模型展开、必需Link/Joint、惯量和Frame自动测试；
- 回退方法：恢复锁定Debian版本；避免依赖新发行版专有宏行为。

## 准入结论

- 状态：已准入；
- 范围：M2及后续机器人描述文件；
- 重新审查条件：Xacro版本升级、生成结果变化或模型拆分规则变更。
