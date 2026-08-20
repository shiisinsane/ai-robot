# W3 ROS 2 接口探查与采集规则

> 日期：2026-08-20  
> 范围：已验收仿真基线的源码、契约与配置；不涉及实体设备

## 1. 已确认接口

| 用途 | 接口 | 结论 |
|---|---|---|
| 任务入口 | `/robot/task/execute` (`ExecuteRobotTask`) | 唯一编排入口；编排器不发布速度 |
| 位姿 | `/robot/pose` | 一秒桶取最后一条，保留 x/y/yaw 三项协方差 |
| 里程计 | `/robot/odom` | 一秒桶计算线/角速度均值及绝对最大值 |
| 障碍距离 | `/robot/scan` | 排除 NaN、Inf 和量程外值后取桶内最小值 |
| 安全停车 | `/robot/safety/stop_active` | 记录桶内是否曾激活 |
| 诊断 | `/robot/diagnostics` | 原样保留名称、级别和消息 |
| TF | `/tf`、`/tf_static` | rosbag 保存；当前结构化位姿优先使用 `/robot/pose` |

Action 的目标、反馈和结果由编排器直接记录；原始 ROS 2 数据继续按 M6 rosbag QoS 规范保存。
`analytics/task_context` 是求职支线内部关联通道，不是机器人公共能力，也不进入主线接口契约。

## 2. 冻结规则

- Ready 最小条件：仿真时钟正常推进，`odom`、`pose`、`scan`、`safety/stop_active`、
  `diagnostics` 可用，公共任务 Action 服务端可用，并且安全停车状态为未激活。
- 有效一秒桶要求 `odom`、`pose`、`scan` 和安全状态均至少一条，且各 Topic 时间戳不倒退。
- 位姿使用桶内最后值；速度报告均值和绝对最大值；雷达报告有效量程内最小值。
- Action 最终位姿是任务结果的权威最终位姿；连续轨迹及协方差来自 `/robot/pose`。
- Action 拒绝只能稳定识别为“服务端拒绝”。当前公共接口不会返回结构化拒绝错误码，因此不推断
  `busy` 或输入错误；需要结合任务管理器日志和 rosbag 复核。
- 当前基线没有稳定的公共 Nav2 恢复/重规划事件接口。W3 将其记为“不可观测”，不根据导航
  反馈文本猜测；`recovery_count`、`replan_count` 在后续 ETL 中应标记来源缺失，而非伪造为零。
- ROS 时间倒退会使对应桶或任务的时钟质量无效；不跨时间跳变拼接任务数据。

## 3. 边界

采集节点没有控制 Publisher。实验编排器只创建 `ExecuteRobotTask` Action 客户端，并发布支线内部
任务上下文；底盘控制、安全停车清除、参数写入和实体接口均不在 W3 范围内。
