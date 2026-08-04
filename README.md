# AI 机器人项目

本仓库用于开发室内差速轮式 AI 机器人。M0“环境与工程基线”、M1“资源、接口与测试
基线”和M2“仿真本体与底盘单元”均已通过正式验收。M3“仿真传感器单元”已于
2026年8月4日启动，M3-W1～W5已完成，当前入口为M3-W6仿真编码器复核；尚未进入实体机器人
或AI Agent开发。

GitHub 仓库：<https://github.com/shiisinsane/ai-robot>

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
│   ├── memo/             # 项目备忘、阶段记录和每日报告
│   └── backs/
│       └── planning/     # 被替代的旧规划版本
├── AGENTS.md
└── README.md
```

## 规划文档规则

- `docs/planning/` 只保留各正式规划系列的最新有效版本。
- `docs/memo/` 保存项目备忘、阶段性记录和按日期连续保留的每日Report。
- 规划正文发生修改时，必须创建新版本文件，不能覆盖旧版本。
- 新版本进入当前目录前，先把被替代版本移动到 `docs/backs/planning/`。
- 默认只依据 `docs/planning/` 中最新版本执行任务；备忘用于补充背景，不能覆盖正式规划。
- 只有追溯历史时才读取 `docs/backs/`。
- 每日Report不进行版本替换，因此始终保留在 `docs/memo/`，不进入`backs`。
- 收到“今日任务已完成”时，应先确认报告归属今日还是昨日，再按确认日期生成文件。

## Skills 目录

`skills/` 保存本项目特有、可重复执行的 AI 代理工作流程，例如规划升级、M0
验收、ROS 2 包创建和接口契约检查。它不用于存放运行时代码，也不代替 `scripts/`
中的自动化脚本。

## 当前阶段入口

当前状态为“M3进行中”，M3-W1～W5已完成，当前入口为M3-W6仿真编码器复核。任务清单见
[`docs/memo/M3任务与验收清单_2026-08-04.md`](docs/memo/M3任务与验收清单_2026-08-04.md)。

M1交付物索引见[`docs/M1交付物索引.md`](docs/M1交付物索引.md)，正式归档位于
`docs/backs/milestones/M1/`；M2正式归档位于`docs/backs/milestones/M2/`。

## 开发环境与统一验证入口

Ubuntu 22.04 环境检查：

```bash
bash scripts/check_environment.sh
```

首次安装后初始化依赖：

```bash
sudo rosdep init
rosdep update
bash scripts/install_dependencies.sh
```

构建、测试和节点验证：

```bash
bash scripts/build.sh
bash scripts/test.sh
bash scripts/check_nodes.sh
```

`check_nodes.sh` 启动两个无运动能力的 M0 状态发布节点，并验证：

- C++：`/m0/cpp_status`
- Python：`/m0/py_status`

Windows/PowerShell 主机检查仍可使用：

```powershell
.\scripts\check_environment.ps1
```

完整依赖、命令和人工 GUI 检查见
[`docs/M0开发环境与复现说明.md`](docs/M0开发环境与复现说明.md)。

## 持续集成

所有拉取请求都会执行仓库基础检查。以下路径发生变更时，还会执行完整的
ROS 2 构建与测试：

- `src/`、`tests/`、`config/`、`test_data/`、`scripts/`
- `.github/workflows/`
- `package.xml`、`CMakeLists.txt`、`setup.py`、`setup.cfg`
- `pyproject.toml`、`requirements*.txt`

仅修改说明文档、`resources/`、议题模板等非运行代码时，完整 ROS 2 检查会
显示为“已跳过”，仓库基础检查仍会正常执行。合入 `main` 后不重复运行完整
ROS 2 检查，以免对同一变更重复消耗执行时间。

## 安全边界

- 当前阶段不接入大模型。
- 当前阶段不进行实体机器人运动测试。
- 未经明确确认，不执行电机、底盘、急停回路或硬件安全相关操作。
- 任何密钥、令牌、Wi-Fi 信息和设备凭据不得提交到 Git。
