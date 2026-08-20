# W4用户运行手册

## 1. 生成实验计划

这一步不启动ROS：

```bash
python3 -m portfolio.robot_ops_analytics.orchestrator.generate_w4_matrix \
  --output /tmp/w4_plan.jsonl
```

预期生成312项。第一版只有`natural__none__none__baseline`环境已标记Ready，共9项；其他分组
必须先准备场景或参数，不能只修改标签冒充实验条件。

## 2. 预览一个批次

```bash
python3 -m portfolio.robot_ops_analytics.orchestrator.run_w4_batch \
  --plan /tmp/w4_plan.jsonl \
  --environment-profile natural__none__none__baseline \
  --experiment-id roa-w4-pilot-001 \
  --output-dir artifacts/roa_w4/roa-data-v0.1/pilot-001/batch_runner \
  --limit 3
```

没有`--execute`时只显示任务，不调用ROS。
要在新批次中精确补采某项计划，可增加`--task-id w4-0002`；该参数可重复传入，脚本会验证任务
确实属于所选环境分组，避免每次`--limit 1`都误选第一项。

## 3. 启动仿真和采集

每个终端使用相同且独立的`ROS_DOMAIN_ID`和`IGN_PARTITION`。依次启动：

1. 对应环境分组的Gazebo、定位和Nav2；
2. M6任务管理器；
3. W3采集器，输出到本批次`structured/records.jsonl`；
4. rosbag，输出到本批次`rosbag/`；
5. 按既有M6流程确认安全停车未激活。

启动前先用`ps -eo pid,ppid,pgid,sid,etimes,comm,args`检查是否存在上一轮Gazebo、Nav2、桥接、
任务管理器、采集器或rosbag残留。每批应使用独立session/process group，并记录主PID、PGID、
ROS域、Gazebo分区和临时目录。发现残留时先按其PGID精确清理，不得使用全局`pkill`或`killall`。

推荐在一个专用终端使用生命周期管理脚本统一启动：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
bash portfolio/robot_ops_analytics/scripts/run_w4_environment.sh \
  --batch-dir artifacts/roa_w4/roa-data-v0.1/pilot-001 \
  --domain-id 205 \
  --partition roa_w4_pilot_001
```

该终端必须保持运行。脚本先单独启动navigation，确认里程计和导航Action可用后才启动任务
管理器，再确认任务Action后启动采集器和rosbag，避免启动竞态并减少空等录包。各组件放入独立
process group，PID/PGID写入`process/`；任一组件异常退出或用户按Ctrl-C时，依次使用SIGINT、
SIGTERM和针对仍存活本批PGID的SIGKILL回收，并生成残留检查记录。

可复用W3命令见`W3_RUNBOOK.md`。正式开始前，人工确认实际障碍、初始偏差和参数版本与
`environment_profile`一致。

## 4. 执行小批次

确认机器人Ready后，在预览命令末尾增加：

```text
--execute --manual-step
```

脚本会在每个任务前显示计划起点，只有你确认场景和机器人已经复位并输入大写`RUN`后才发任务。
建议第一次保留`--limit 3`。任务失败时脚本默认停止批次并保留日志。排查原因后新建批次继续，
不要覆盖原结果。只有明确希望继续收集后续任务时才使用`--continue-on-failure`。

已通过人工Pilot验证基础链路后，可用安全总控脚本执行起终点连续的一组任务：

```bash
bash portfolio/robot_ops_analytics/scripts/run_w4_safe_group.sh \
  --batch-dir artifacts/roa_w4/roa-data-v0.1/pilot-004 \
  --domain-id 209 \
  --partition roa_w4_pilot_004 \
  --experiment-id roa-w4-pilot-004 \
  --plan artifacts/roa_w4/roa-data-v0.1/pilot-004/plan.jsonl \
  --task-id w4-0055 \
  --task-id w4-0109
```

总控脚本自动等待环境Ready、调用公开安全服务清除启动故障、确认`stop_active=false`、顺序发送
显式指定的任务，并在正常、失败、超时或中断时调用环境控制器清理。自动模式只接受同一已冻结
环境分组中起终点连续的任务，不能用它跳过场景准备或自动复位要求。运行期间仍需人工观察Gazebo；
发现碰撞、持续旋转或其他危险迹象时按`Ctrl-C`。

## 5. 汇总批次

```bash
python3 -m portfolio.robot_ops_analytics.orchestrator.summarize_w4_batch \
  --results artifacts/roa_w4/roa-data-v0.1/pilot-001/batch_runner/run_results.jsonl
```

这里的`runner_success`只表示单任务编排器返回0，正式任务标签仍以采集器JSONL中的Action终态
和错误码为准，W5 ETL不得只依赖批处理返回码。

## 6. 数据位置

- 结构化ROS数据：`structured/records.jsonl`；
- 原始ROS消息：`rosbag/rosbag_*.db3`及`metadata.yaml`；
- 每次任务的脚本日志：`batch_runner/task_logs/`；
- 批次执行索引：`batch_runner/run_results.jsonl`；
- 本批使用的计划：`plan.jsonl`；
- 后续生成的证据清单：`evidence_manifest.yaml`。

这些大文件均位于`artifacts/`，不会进入Git。每批结束后应备份到可靠外部存储并记录SHA-256。

## 7. 用户观察重点

- Gazebo里的场景是否与分组标签一致；
- 机器人是否碰撞、卡死、持续旋转或异常瞬移；
- 安全停车是否正常生效；
- 一个任务结束后是否仍有活动导航目标；
- 场景或参数切换后是否误用了上一批配置；
- 采集器和rosbag是否在整个批次持续运行。
- 每个任务前机器人是否确实位于计划起点，而不是停在上一任务目标点。

## 8. 结束与无残留检查

正常完成、失败、超时或人工中断都必须执行同一清理流程：向本批独立process group发送终止
信号，等待Gazebo、Nav2、`ros_gz_bridge`、任务管理器、采集器和rosbag全部退出。不得只停止
顶层bash或`ros2 launch`。

清理后再次执行启动前的`ps`检查，并结合本批记录的PID、PGID、SID、ROS域和Gazebo分区确认
无残留。检查结果应写入批次日志；只要仍有本批进程，就不得验收该批或启动下一批。
