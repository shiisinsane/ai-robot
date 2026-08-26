# W6核心SQL清单

> 版本：v0.1
> 日期：2026-08-25
> 状态：00～09已实现并在`roa-data-v0.1`正式DuckDB上执行

| 顺序 | 文件 | 输入 | 输出粒度 | 业务用途 |
|---:|---|---|---|---|
| 0 | `00_data_contract_checks.sql` | 三张事实视图 | 单行门禁结果 | 阻止重复主键、空值或跨层数量错误进入分析 |
| 1 | `01_overall_kpis.sql` | 任务事实 | 整体、终态 | 建立任务量、完成率和周期基线 |
| 2 | `02_cycle_time_distribution.sql` | 任务事实 | 整体、终态、路线 | 计算均值与P50/P90/P95，识别长尾 |
| 3 | `03_scenario_failure_breakdown.sql` | 任务事实 | 路线×障碍×扰动 | 比较样本量、失败率和失败贡献度 |
| 4 | `04_failure_pareto.sql` | 任务事实 | 场景组合、错误码 | 排序主要失败来源，不把高失败率等同高贡献 |
| 5 | `05_stage_duration.sql` | 事件事实 | 任务×阶段 | 计算阶段近似停留并定位卡点 |
| 6 | `06_preterminal_telemetry.sql` | 遥测、任务事实 | 任务 | 提取早期和终态前遥测特征 |
| 7 | `07_safety_guardrails.sql` | 遥测、任务事实 | 整体、场景 | 检查障碍距离、停车、过期和覆盖率 |
| 8 | `08_failure_streaks.sql` | 任务事实 | 连续任务段 | 检查失败是否按时间或批次聚集 |
| 9 | `09_anomaly_candidates.sql` | 前述预聚合结果 | 异常候选 | 形成补采优先级和机制假设输入 |

## 编写规范

- 方言：DuckDB SQL；
- 每个文件开头写业务问题、输入粒度、过滤条件、输出粒度和限制；
- 正式任务口径限定`dataset_version='roa-data-v0.1'`、`run_origin='natural'`、
  `data_quality_valid=TRUE`；
- 分组输出必须包含`task_count`，失败分析同时包含`failure_count`、`failure_rate`和
  `failure_contribution`；
- 分位数统一使用`quantile_cont`，不得把均值称为典型耗时；
- 事件和遥测先聚合到每任务一行再与任务事实连接；
- 禁止对跨事实的一对多Join直接使用`COUNT(*)`表示任务数；无法预聚合时必须使用
  `COUNT(DISTINCT task_id)`；
- SQL观察结果只写“相关”“集中”“差异”，控制变量实验完成前不写“导致”。
