# 简历项目经历

## 推荐项目名称

**机器人测试数据分析与实验决策系统｜实习项目**
Python、SQL、DuckDB、SQLite、数据建模、ETL、实验设计、Bootstrap、ROS 2/Gazebo

## 中文四条版

- 面向公共空间环境检查与物品传递机器人的仿真测试，构建任务级指标体系，定义单位仿真时间有效任务数、
  完成率、周期分位数、阶段失败率及安全护栏，并明确统计粒度、分子分母、过滤规则和时间口径。
- 针对任务状态、ROS事件与遥测分散、测试结果难追溯的问题，设计任务、事件、遥测及实验维度模型，
  使用Python构建可复现ETL与质量门禁，将32,866条原始
  记录加工为45项正式任务、9,725条事件和1,759个遥测桶；通过21条规则隔离7次无效尝试。
- 编写SQL拆解完成率、周期长尾、失败场景及安全指标，并与独立Python计算逐项核对，39项结果在
  `1e-9`容差内一致，控制Join膨胀、测试污染和指标口径漂移。
- 识别早期障碍测试中路线、障碍位置与端点几何混杂，重设计45项预注册平衡区组实验；基于区组留一
  回放进一步比较任务预算，在平均预算
  近似45秒时，难度分档P90将最终成功任务的潜在升级标记由15/45降至7/45，并明确结果仅用于
  后续仿真策略验证。

## 一页简历三条版

- 面向机器人仿真测试构建任务级指标体系和分析数据模型，将“运行得好不好”拆为任务吞吐、完成能力、周期
  效率、阶段失败和安全护栏，并将口径落实到SQL与质量测试。
- 搭建Python/SQL数据链路，将分散的32,866条ROS 2仿真记录加工为可追溯事实表，以21条质量规则隔离
  无效实验，并完成39项SQL/Python独立对账。
- 识别实验混杂并重做45项预注册区组实验；通过样本外情景回放发现，在近似45秒平均预算下，难度
  分档P90将最终成功任务的潜在升级标记从15项降至7项，为后续策略实验提供候选规则。

## 英文版

- Built a task-level KPI framework for simulation testing of a public-space service robot, covering throughput, completion,
  cycle-time percentiles, stage-level failures, and safety guardrails with explicit grains, formulas, filters,
  and time definitions.
- Built a reproducible Python/SQL pipeline that transformed 32,866 fragmented ROS 2 records into traceable task, event,
  and telemetry facts; enforced 21 quality checks and reconciled 39 SQL metrics against independent Python
  calculations within a 1e-9 tolerance.
- Identified confounding and redesigned a 45-run preregistered balanced-block study; in leave-one-block-out
  scenario replay at an approximately 45-second mean budget, a difficulty-aware P90 policy reduced potential
  escalation flags on ultimately successful tasks from 15/45 to 7/45, motivating further simulation testing.

## 使用规则

- 投递数据分析/商业分析：把“指标体系”和“SQL诊断”放在前两条。
- 投递数据科学：把“实验设计”和“数据泄漏防范”放在前两条。
- 投递数据工程偏分析：把“数据模型、ETL、质量规则和对账”放在前两条。
- 不写尚未完成的PR-AUC、召回率或生产收益。
