# diagnostic_updater 4.0.7资源卡

## 基本信息

- 对象：M4诊断发布与安全监督可观察性；
- 上游仓库：`https://github.com/ros/diagnostics`；
- 项目文档：`https://docs.ros.org/en/humble/p/diagnostic_updater/`；
- Ubuntu 22.04/Humble候选包：`ros-humble-diagnostic-updater`；
- 候选版本：`4.0.7-1jammy.20260605.155607`；
- 消息基线：本机`diagnostic_msgs 4.9.1`已安装；
- 许可证：BSD风格许可证，以候选二进制包和上游`LICENSE`为准；
- 当前状态：已准入，本机版本、BSD-3-Clause许可证及ROS 2包发现已验证。

## 采用范围

用于把安全监督、传感器新鲜度和关键链路状态发布到M1冻结的`/robot/diagnostics`。安全规则、
命令所有权、锁存故障和清除条件由项目普通Python逻辑实现；`diagnostic_updater`不承担安全
决策，也不替代实体急停或MCU保护。

## 准入理由与验证要求

- 使用ROS标准`DiagnosticArray`，不新增临时字符串或私有JSON公共接口；
- W2冻结状态级别、错误码、超时和发布频率；
- W7验证正常、WARN、ERROR、锁存、清除和停车链；
- 更新器异常不得形成绕过安全监督的路径；失败时安全侧按关键状态不可用处理。
