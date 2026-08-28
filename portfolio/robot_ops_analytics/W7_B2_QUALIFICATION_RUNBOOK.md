# W7 B2资格Pilot运行手册

> 状态：第2项发现定位连续性异常后已暂停；不授权正式采集
> 范围：15项GUI资格Pilot，不进入B2正式建模数据

面向手动操作者的简化复现步骤见`W7_B2_GUI_REPRODUCTION_GUIDE.md`。

## 1. 离线生成与预览

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.b2_v0_3.generate_w7_b2_qualification_plan \
  --output portfolio/robot_ops_analytics/plans/b2_v0_3/w7_b2_qualification_plan_v0.1.jsonl
```

计划包含5条路线×none/low/medium障碍，共15项。候选ROS域为140～154，每项使用独立Gazebo
Transport分区。该JSONL是资格路线与环境组合的版本化冻结运行计划，不能以`/tmp`副本作为
正式证据来源；`/tmp`只允许用于生成器开发预览。当前资格执行已暂停，不允许启动后续Pilot或
360项正式采集；已明确授权的单项诊断须写入独立diagnostic批次目录。

## 2. 单项运行边界

人工诊断优先使用封装入口。操作者只选择冻结计划中的`task-id`和本轮唯一`run-id`；路线起点、
终点、障碍、环境分组、定位扰动、ROS候选域及Gazebo分区均由程序解析。默认只预览，确认后增加
`--execute`才启动GUI：

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.b2_v0_3.run_w7_b2_diagnostic --list

python3 -m portfolio.robot_ops_analytics.pipelines.b2_v0_3.run_w7_b2_diagnostic \
  --task-id b2-pilot-horizontal_center-low \
  --run-id manual_diagnostic_003

python3 -m portfolio.robot_ops_analytics.pipelines.b2_v0_3.run_w7_b2_diagnostic \
  --task-id b2-pilot-horizontal_center-low \
  --run-id manual_diagnostic_003 \
  --execute
```

该入口只用于已明确授权的单项诊断，不改变资格暂停状态，也不准入正式数据。

实际执行时一次只启动一个Pilot。启动前检查同类ROS/Gazebo残留；每项使用安全总控脚本、GUI、
独立域和独立分区。先从计划生成该任务专用障碍配置，再传给安全总控。资格任务使用
`--qualification-pilot --gui --no-history`，其中`no_history`只因Pilot不进入正式数据。

不得并行运行15项，不得在GUI异常、Nav2生命周期未Active、任务前快照缺失或清理残留未归零时
启动下一项。正式执行脚本将在用户授权并把资格配置切换为授权状态后补齐；当前不提供可绕过状态
门禁的一键执行入口。

## 3. 每项人工确认

- 起点、终点与计划一致；
- 障碍档位和实际位置与单项配置一致；
- medium场景存在全局规划且障碍不覆盖起终点；
- 机器人实际移动，轨迹合理；
- 无碰撞、异常瞬移、持续旋转或长时间卡死；
- Action终态与结构化记录一致；
- `preacceptance_snapshot`早于`requested`且字段完整；
- 本轮process group、ROS域和Gazebo分区相关残留全部清零。

单项成功不自动放行整条路线。15项全部完成并复核后，才能决定路线/障碍资格是否通过以及是否
冻结B2正式预注册。
