# W7 B2 GUI单项诊断复现说明

> 适用范围：`portfolio/robot_ops_analytics/`求职支线的W7 B2单项仿真诊断
> 当前边界：资格流程因第2项历史异常保持暂停；本说明不授权后续资格Pilot或正式数据采集
> GUI启动责任：由用户在本机终端手动执行`--execute`命令；AI代理不代替用户启动GUI
> 已验证示例：`manual_diagnostic_003`，2026-08-28

## 1. 目标

使用一个简化入口，从冻结的15项资格计划中选择一个任务，自动完成参数解析、障碍配置生成、
Gazebo GUI、Nav2任务、结构化采集、rosbag和进程清理。操作者不再手工拼接起点、终点、障碍、
环境分组和Gazebo分区等底层参数。

本流程中的“手动启动”是指用户亲自在终端输入封装命令并决定何时增加`--execute`。封装程序会
自动启动组成一套实验的Gazebo、Nav2、采集器和rosbag；不要求用户分别打开多个终端或逐个启动
底层节点。

操作者与程序的职责边界：

| 环节 | 用户负责 | 程序负责 |
|---|---|---|
| 任务选择 | 选择`task-id` | 从冻结计划读取全部任务参数 |
| 本轮标识 | 输入唯一`run-id` | 生成输出路径、实验ID和Gazebo分区 |
| 启动决定 | 检查预览后亲自增加`--execute` | 启动整套隔离环境 |
| GUI验收 | 观察起点、绕障、终点和异常运动 | 记录结构化数据、日志和rosbag |
| 停止 | 正常等待结束，异常时按一次`Ctrl+C` | 回收本轮进程组并检查残留 |
| 最终判断 | 报告GUI观察 | 执行自动校验；两者共同决定结果 |

## 2. 环境准备

```bash
cd /home/yangyiyao/ai_robot
source /opt/ros/humble/setup.bash
source install/setup.bash
```

启动前不得存在另一套Gazebo/Nav2实验。封装入口还会调用安全总控脚本执行残留检查；发现同类
进程时会拒绝启动。

## 3. 查看可选任务

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.b2_v0_3.run_w7_b2_diagnostic \
  --list
```

输出15个可选`task-id`。任务来自正式冻结计划：

```text
portfolio/robot_ops_analytics/plans/b2_v0_3/w7_b2_qualification_plan_v0.1.jsonl
```

## 4. 预览单项任务

以水平中央路线、low障碍为例：

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.b2_v0_3.run_w7_b2_diagnostic \
  --task-id b2-pilot-horizontal_center-low \
  --run-id manual_diagnostic_004
```

默认只预览，不启动ROS或GUI。应检查终端显示的任务、起点、终点、障碍、ROS域、Gazebo分区和
输出目录。`run-id`必须是本轮唯一名称；已经存在的输出目录不会被覆盖。

## 5. 用户手动启动GUI并执行

确认预览中的任务、起终点、障碍、域号和输出目录均正确后，由用户本人在同一终端执行以下命令。
增加`--execute`才会真正启动GUI：

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.b2_v0_3.run_w7_b2_diagnostic \
  --task-id b2-pilot-horizontal_center-low \
  --run-id manual_diagnostic_004 \
  --execute
```

按下回车后，用户不需要再输入底层ROS命令。终端依次出现以下信息属于正常过程：

```text
执行B2冻结计划与运行参数一致性门禁...
B2启动参数与冻结计划一致性门禁：通过
启动W4环境
等待环境完成分阶段Ready
环境Ready
配置并记录障碍物档位
开始顺序执行
```

如果一致性门禁失败，程序会在ROS/Gazebo启动前退出。此时不要绕过门禁或改用旧的长命令，
应保留终端报错并检查冻结计划与本轮参数。

程序自动执行：

1. 从冻结计划读取路线起点、终点、障碍档位、障碍位置、定位扰动和候选ROS域；
2. 在本轮目录生成`config_runtime/obstacle.yaml`；
3. 设置独立的`ROS_DOMAIN_ID`和Gazebo Transport分区；
4. 启动Gazebo、Nav2、任务管理器、采集器和rosbag；
5. 检查位姿、雷达、诊断、Nav2生命周期、任务Action与安全停车状态；
6. 发送单项导航任务；
7. 任务结束后统一回收本轮进程组并检查残留。

中途需要停止时，在运行命令所在终端按一次`Ctrl+C`，等待统一清理完成。不要直接关闭终端，
也不要使用全局`pkill`或`killall`。

任务正常结束后GUI会由程序关闭，终端重新出现Shell提示符。用户应记录自己的GUI观察，至少回答：

1. 机器人是否在预览所示起点出现；
2. 障碍物位置和档位是否合理；
3. 机器人是否沿合理路径到达目标；
4. 是否出现碰撞、瞬移、掉头返回、持续旋转或卡死。

## 6. GUI人工观察要求

示例任务`b2-pilot-horizontal_center-low`应表现为：

- 机器人从地图左侧`(-2.0, 0.0, 0.0)`出现；
- 临时障碍位于路线中部偏上方，约为`(0.0, 0.75, 0.45)`；
- 机器人从左向右运动，合理绕开障碍；
- 在右侧目标`(2.0, 0.0, 0.0)`附近停止；
- 不出现碰撞、异常瞬移、掉头返回起点方向、持续旋转或长时间卡死。

终端中的：

```text
初始位姿扰动已冻结：none，位姿={'x': 0.0, 'y': 0.0, 'yaw': 0.0}
```

表示人为施加的定位扰动偏移量为零，不表示机器人出生在地图中心。真实出生位置由冻结计划的
`start_x/start_y/start_yaw`自动传入，本示例为`(-2.0, 0.0, 0.0)`。

## 7. 输出数据

若`run-id`为`manual_diagnostic_004`，所有产物位于：

```text
artifacts/roa_b2/manual_diagnostic_004/
```

主要文件：

```text
config_runtime/obstacle.yaml                 本轮障碍输入
config_snapshot/obstacle_environment.json    实际生效的障碍快照
config_snapshot/initial_perturbation.json    定位扰动快照
structured/records.jsonl                     任务事件与每秒遥测
rosbag/w4_pilot_bag/                         ROS原始消息
batch_runner/run_results.jsonl               任务执行索引与返回码
batch_runner/task_logs/                      单任务日志
runtime_logs/navigation.log                  Nav2与AMCL日志
runtime_logs/task_manager.log                任务管理器日志
runtime_logs/collector.log                   采集器日志
process/environment.txt                      域、分区和真实初始位姿
process/process_groups.tsv                    本轮PID与PGID
process/residue_check.txt                    清理验收结果
```

诊断产物不自动进入B2正式建模数据集。

## 8. 自动校验

GUI关闭并回到Shell提示符后，由用户在同一终端手动执行：

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.common.validate_w4_sample \
  --batch-dir artifacts/roa_b2/manual_diagnostic_004 \
  --task-id b2-pilot-horizontal_center-low
```

正常输出：

```text
valid_success
```

该校验包含任务终态、遥测完整性、安全停车、位姿连续性、rosbag、Runner返回码和进程残留门禁。
仍必须结合GUI人工观察，自动成功不能覆盖异常运动。

执行完校验后，把以下内容反馈给AI代理即可继续分析，无需发送全部日志：

```text
run-id：
GUI观察：正常 / 异常及现象
自动校验输出：
residue_check输出：
```

清理结果可单独查看：

```bash
cat artifacts/roa_b2/manual_diagnostic_004/process/residue_check.txt
```

正常输出：

```text
本批进程组残留检查：通过
```

## 9. 已验证复现记录

2026-08-28，用户使用：

```text
task-id = b2-pilot-horizontal_center-low
run-id  = manual_diagnostic_003
```

完成GUI人工复现并确认运动正确。离线复核结果：

- 自动校验：`valid_success`；
- 结构化记录：902行；
- rosbag：存在且通过消息门禁；
- 清理：`本批进程组残留检查：通过`；
- 数据性质：单项诊断证据，不准入正式B2数据集。

## 10. 常见问题

### 诊断复现与正式资格重跑是否相同

不同。本文件当前使用`run_w7_b2_diagnostic`，输出是诊断证据，不自动改写资格进度，也不进入
正式建模数据。正式重跑第2项资格Pilot必须在资格暂停问题关闭、执行范围再次确认并使用资格批次
命名后进行。不得把`manual_diagnostic_*`目录重命名或事后宣称为正式资格样本。

### 输出目录已经存在

不得覆盖旧证据。把`run-id`递增，例如从`manual_diagnostic_004`改为
`manual_diagnostic_005`。

### GUI中机器人出现在中心

立即按`Ctrl+C`停止并等待清理。封装入口会从计划自动传入起点；若仍异常，检查：

```bash
cat artifacts/roa_b2/<run-id>/process/environment.txt
```

其中`initial_pose`必须与预览起点一致。

### 自动显示成功但GUI运动异常

该轮仍判为不通过，不启动下一项。保留整个批次目录，并检查`structured/records.jsonl`和
`runtime_logs/navigation.log`。

## 11. 第2项正式资格重跑（历史入口）

本节只适用于当前明确授权的第2项重跑，不放行第3～15项。先预览：

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.b2_v0_3.run_w7_b2_qualification_rerun \
  --retry 1
```

确认预览中的任务、起点、终点和障碍正确后，由用户本人增加`--execute`启动GUI：

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.b2_v0_3.run_w7_b2_qualification_rerun \
  --retry 1 \
  --execute
```

如果`retry-001`目录已经存在，不得覆盖，应把两条命令中的`--retry 1`同时改为`--retry 2`。
GUI观察标准与第6节相同。运行结束后，使用终端预览显示的资格批次目录执行第8节自动校验，并把
GUI观察、`valid_success/失败原因`和残留检查结果反馈给AI代理。该入口不会自动启动下一项。

## 12. 当前授权资格任务（用户手动启动）

从第3项开始，使用统一入口。它只读取资格配置中当前明确授权的一项，不能通过命令行任意跳到
其他任务。先预览：

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.b2_v0_3.run_w7_b2_qualification_task \
  --attempt 1
```

核对任务、起终点、障碍、ROS域、Gazebo分区和输出目录后，由用户本人增加`--execute`：

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.b2_v0_3.run_w7_b2_qualification_task \
  --attempt 1 \
  --execute
```

同一任务需要重试时递增`--attempt`，不得覆盖旧目录。该入口不会自动放行下一项，也不会把资格
Pilot准入360项正式数据集。
