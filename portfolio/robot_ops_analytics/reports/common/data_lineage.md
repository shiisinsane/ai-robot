# W2 数据血缘与字段来源

> 版本：roa-schema-v1.0  
> 日期：2026-08-19

## 1. 数据流

```text
实验配置与证据清单 ───────────────→ dim_experiment / dim_scenario / dim_route
M5、M6 配置与契约 ────────────────→ dim_parameter_version / dim_error_code
ExecuteRobotTask Goal/Feedback/Result ─→ fact_task_execution / fact_task_event
TF、pose、odom、scan、安全与诊断 Topic ─→ 一秒聚合 → fact_task_telemetry_1s
任务事件和遥测聚合 ───────────────→ fact_task_execution 派生特征
机器人 Ready 与 /clock 质量区间 ─────→ fact_robot_operation_window
```

## 2. 主要字段来源

| 分析字段 | 原始来源 | 转换规则 |
|---|---|---|
| `task_id` | `ExecuteRobotTask.Goal.task_id` | 原样保存并校验唯一性 |
| `task_type` | Action Goal | 原样保存 |
| 目标位姿 | Action Goal `target_pose` | 统一为 `map` 坐标和 yaw |
| `accepted` | Action goal handle | 接受为真，拒绝为假 |
| 任务阶段 | Action Feedback `phase` | 映射为有序事件 |
| `terminal_status` | Action 状态与 Result | 规范化为 success/failed/canceled/timeout/rejected |
| `error_code` | Action Result | 关联 `dim_error_code`，不改原值 |
| 最终位姿 | Action Result `final_pose` 或 TF | 统一到 `map`；来源需记录 |
| 到点快照可用性 | `SensorSnapshot` | 映射 scan/image/pose available 字段 |
| 位姿和协方差 | `/robot/pose` | 一秒窗口取末值或统计值，规则在 W3 冻结 |
| 线速度和角速度 | `/robot/odom` | 一秒窗口计算均值和绝对最大值 |
| 最小雷达距离 | `/robot/scan` | 排除 NaN、Inf 和量程外值后求最小值 |
| 安全停车 | `/robot/safety/stop_active` | 记录状态、边沿事件和任务级触发次数 |
| 传感器过期 | `/robot/diagnostics` 与时间戳 | 按冻结新鲜度门限生成位掩码和事件数 |
| 恢复和重规划 | Nav2 状态/事件适配 | W3 明确可观测来源；不可可靠采集时标记缺失，不推断 |
| 实际路径长度 | 连续有效位姿 | 相邻位姿增量累计，跳变先进入质量检查 |
| 机器人运行窗口 | Ready 状态与 `/clock` | 只保留可接单且时钟正常推进的区间 |

## 3. 原始数据与分析数据关系

rosbag 是可回放原始证据，事实表不是原始证据的替代品。每批分析数据必须通过
`experiment_id`、证据清单和数据版本关联到对应 rosbag 或结构化采集日志。大型原始数据不进入
普通 Git，只保存位置、大小、哈希和复现命令。

## 4. W3 待确认项

- Nav2 恢复和重规划是否存在稳定、无需修改正式基线的只读观测来源；
- 任务被拒绝时能否稳定获得拒绝原因；
- Ready 状态的最小可靠组合；
- TF 与 Action `final_pose` 同时存在时的优先级；
- 一秒桶内位姿协方差使用末值、最大值或二者同时保存；
- 必需 Topic 集合和有效遥测桶判定。

这些问题必须通过 W3 接口探查解决，不能用猜测字段填充。

