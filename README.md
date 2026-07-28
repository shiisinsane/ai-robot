# AI 机器人项目

本仓库用于开发室内差速轮式 AI 机器人。当前只执行 ROS 2 机器人开发规划中的
M0“环境与工程基线”，尚未进入仿真机器人开发、实体机器人测试或 AI Agent 开发。

## 技术基线

- Ubuntu 22.04
- ROS 2 Humble
- VS Code
- C++ / Python
- `colcon`
- RViz2
- Gazebo

当前仓库可能由 Windows 主机访问，但 ROS 2 Humble 的正式构建、测试和运行基线以
Ubuntu 22.04 环境为准。

## 目录结构

```text
.
├── src/
│   ├── robot_core/       # M0～M11：ROS 2机器人部分
│   └── ai_agent/         # M12～M17：G2通过前仅预留
├── config/
│   ├── common/
│   ├── sim/
│   └── real/
├── maps/
├── tests/
│   ├── unit/
│   ├── node/
│   ├── contract/
│   ├── integration/
│   ├── simulation/
│   └── real/
├── test_data/
├── resources/
├── scripts/
├── skills/               # 项目专用、可复用的代理工作流程
├── docs/
│   ├── planning/         # 当前生效的正式规划
│   ├── memo/             # 当前项目备忘和阶段性记录
│   └── backs/
│       ├── planning/     # 被替代的旧规划版本
│       └── memo/         # 被替代的旧备忘版本
├── AGENTS.md
└── README.md
```

## 规划文档规则

- `docs/planning/` 只保留各正式规划系列的最新有效版本。
- `docs/memo/` 保存当前备忘和阶段性记录。
- 规划正文发生修改时，必须创建新版本文件，不能覆盖旧版本。
- 新版本进入当前目录前，先把被替代版本移动到 `docs/backs/` 下对应分类。
- 默认只依据 `docs/planning/` 中最新版本执行任务；备忘用于补充背景，不能覆盖正式规划。
- 只有追溯历史时才读取 `docs/backs/`。

## Skills 目录

`skills/` 保存本项目特有、可重复执行的 AI 代理工作流程，例如规划升级、M0
验收、ROS 2 包创建和接口契约检查。它不用于存放运行时代码，也不代替 `scripts/`
中的自动化脚本。

## M0 当前入口

Windows/PowerShell 主机检查：

```powershell
.\scripts\check_environment.ps1
```

Ubuntu 22.04 环境检查：

```bash
bash scripts/check_environment.sh
```

脚本只进行只读检查，不会安装或删除软件。

## 安全边界

- 当前阶段不接入大模型。
- 当前阶段不进行实体机器人运动测试。
- 未经明确确认，不执行电机、底盘、急停回路或硬件安全相关操作。
- 任何密钥、令牌、Wi-Fi 信息和设备凭据不得提交到 Git。
