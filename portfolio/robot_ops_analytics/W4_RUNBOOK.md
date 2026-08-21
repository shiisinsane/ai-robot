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

新环境档位首次资格验证时，在总控命令增加`--gui`打开Gazebo。人工确认场景标签与画面一致后，
后续同档位重复采集可省略该参数。GUI进程仍属于navigation进程组，会走相同的精确清理流程。

低障碍资格Pilot通过后，剩余8项可串行自动执行：

```bash
bash portfolio/robot_ops_analytics/scripts/run_w4_low_obstacle_campaign.sh \
  --start-domain 213
```

该脚本执行5套环境：两个短路线复位批次，以及三组“长出+返回”连续任务。每套使用独立批次
目录、ROS域和Gazebo分区；只有前一套安全总控返回成功（包括正式无残留门禁）才启动下一套。
任一任务、环境配置或清理失败都会停止Campaign。汇总索引写入
`artifacts/roa_w4/roa-data-v0.1/low-obstacle-campaign-results.tsv`。

中难度障碍的首次候选位置`(0.4, 0.6, 0.45)`于2026-08-21执行`w4-0037`资格
Pilot；任务成功且无碰撞，但机器人保持直行，因未形成可见路径调整而未通过中难度
资格。该批证据保留，不计入正式W4数据集。

二次候选位置为`(0.4, 0.45, 0.45)`，改用`(0.0, 0.0) → (0.8, 0.0)`长路线。红色障碍
尺寸为`0.55m`，其边缘距路线中心线`0.175m`，小于机器人`0.205m`半宽，直行安全
包络重叠`0.03m`；长路线为绕行后回正留出空间。该档位仍为`environment_ready=false`，
只能使用单项GUI资格Pilot：

二次候选于2026-08-21执行`w4-0091`资格Pilot；障碍距小车过近，小车未运动即以
`error_code=201`导航失败，最小雷达距离约`0.195m`，因此也未通过。证据保留在
`medium-pilot-002`，不计入正式W4数据集。

三次候选改为`(0.4, 0.52, 0.45)`，障碍边缘距路线中心线`0.245m`，较机器人
`0.205m`半宽保留约`0.04m`几何间隙，同时仍位于Nav2障碍膨胀区内。
该候选于2026-08-21的`medium-pilot-003`和`medium-pilot-004`尚未完成资格验证：前者因
NVIDIA PGRAPH/EGL上下文失败导致navigation Ready超时，后者尝试软件OpenGL时Gazebo GUI
在`QOpenGLContext::doneCurrent()`段错误退出。两批均未发送任务、无残留进程，不计入W4数据集。
图形环境恢复前不得反复重启GUI，也不得以无GUI任务成功代替人工资格确认。

图形环境恢复后，`medium-pilot-006`完整执行了`(0.4, 0.52, 0.45)`长路线Pilot。小车
原地旋转至约`-1.10rad`、几乎无线位移，最小雷达距离约`0.25m`，以`error_code=201`
失败；人工确认无碰撞，但不符合“可前进绕行”资格。四次候选因此调整为
`(0.4, 0.56, 0.45)`，障碍边缘距路线中心线`0.285m`，较机器人半宽保留约`0.08m`。

`medium-pilot-007`已于2026-08-21通过资格验证：`w4-0091`成功、`error_code=0`，小车
最大横向偏移约`0.47m`、最小有效雷达距离约`0.284m`；人工确认小车实际前进绕行、
无碰撞或卡死，到点后的若干次小角度旋转为目标航向校正。Action终态、结构化
记录和rosbag一致，残留检查通过。`medium`因此正式冻结为`(0.4, 0.56, 0.45)`
并设为Ready；该Pilot计入W4正式数据集。

资格通过后已完成其余8项中障碍正式采集。`w4-0037`～`w4-0039`、`w4-0092`和
`w4-0093`成功；`w4-0145`～`w4-0147`均到达公开导航Action后以`error_code=201`、
Action状态6失败。三项失败均有有效时间戳、完整必需Topic、`stop_active=false`遥测和
可读rosbag，Nav2日志记录规划器无法生成回到`(0.0, 0.0)`的有效路径，属于中障碍下的
真实返回失败而非环境异常，因此保留为正式失败样本。所有执行批次的进程组残留检查通过。
至此中障碍档位共9项（成功6、失败3），W4累计27/312项；下一步进入低档初始位姿与
航向扰动的首次GUI资格验证。障碍档位只有`none`、`low`和`medium`三档，不设置`high`档。

低档初始位姿扰动`(x=0.05m, y=0.0m, yaw=0.05rad)`已于2026-08-21通过
`initial-low-pilot-001`单项GUI资格验证：Gazebo机器人真值出生位姿与AMCL初值施加同一
扰动，`w4-0007`成功；人工确认小车从轻微偏转位置启动，平稳修正并到达目标，无持续旋转、
卡死、碰撞或异常跳动。配置快照、Action结果和rosbag已保存，进程组残留检查通过。该Pilot
计入正式数据集，低档扰动设为Ready，W4累计28/312项，剩余26项待串行采集。

低档扰动27项已于2026-08-21全部完成，其中21项成功、6项真实导航失败。除既有
`w4-0025`外，`w4-0079`和`w4-0097`分别在低、中障碍长路线失败，`w4-0151`～`w4-0153`
在中障碍返回路线失败；各失败任务均具备唯一Action终态、完整有效遥测、可读rosbag和
清理证明，按数据集规则保留。当前W4累计54/312项，下一步进入中档初始位姿扰动资格Pilot。

2026-08-21完成数据目录增量审计。无效、中断或已被重试替代的批次已从
`artifacts/roa_w4/roa-data-v0.1/`移至`artifacts/roa_w4/rejected-v0.1/`，拒收原因记录在
`rejection_manifest.jsonl`；隔离数据未永久删除。正式目录当前包含54个唯一有效任务，
其中45项成功、9项真实任务失败。Campaign期间因工作区环境未加载、受限执行环境以及两次
网络中断产生的未发任务批次均已隔离，不计入正式口径。

```bash
python3 -m portfolio.robot_ops_analytics.orchestrator.generate_w4_matrix \
  --output artifacts/roa_w4/roa-data-v0.1/medium-pilot-001/plan.jsonl
bash portfolio/robot_ops_analytics/scripts/run_w4_safe_group.sh \
  --batch-dir artifacts/roa_w4/roa-data-v0.1/medium-pilot-001 \
  --domain-id 220 --partition roa_w4_medium_pilot_001 \
  --experiment-id roa-w4-medium-pilot-001 \
  --plan artifacts/roa_w4/roa-data-v0.1/medium-pilot-001/plan.jsonl \
  --environment-profile natural__medium__none__baseline \
  --obstacle-profile medium --task-id w4-0091 \
  --qualification-pilot --gui
```

人工必须确认：障碍未覆盖起点/目标；机器人产生可见的减速或绕行；无碰撞、卡死、
持续旋转或异常瞬移；任务终态成功；结构化记录与rosbag可对账；清理无残留。全部
通过后才可将`medium.environment_ready`改为`true`；仅任务返回成功不足以放行。

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
