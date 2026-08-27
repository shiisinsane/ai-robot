# W3 结构化采集运行手册

> 仅用于仿真。不得连接实体机器人或使用默认 ROS 域。

## 1. 启动约束

同一次运行的全部终端必须使用相同的独立 `ROS_DOMAIN_ID` 和 Gazebo Transport 分区。例如：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=187
export IGN_PARTITION=roa_w3_187
```

先按 M6 已验收方式启动仿真、定位、Nav2 和任务管理器。若 ROS 图中出现无关节点、Frame 或
同名节点，应停止并换用干净域重新启动，不得继续采集。

## 2. 启动只读采集器

采集器必须放在 `/robot` 命名空间，使相对 Topic 与公共契约一致：

```bash
python3 -m portfolio.robot_ops_analytics.collector.ros_collector \
  --ros-args -r __ns:=/robot -p use_sim_time:=true \
  -p output_path:=/tmp/roa_w3_records.jsonl
```

## 3. 运行单个确定性任务

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.common.run_experiment \
  --experiment-id roa-w3-smoke-001 --task-id roa-w3-task-001 \
  --x 0.8 --y 0.0 --yaw 0.0 --timeout 90 \
  --ros-args -r __ns:=/robot -p use_sim_time:=true
```

编排器会先确认任务 Action、五个必需 Topic 和仿真时钟均 Ready，再发送任务。它只调用
`task/execute`，不会发布 `cmd_vel` 或调用安全清除服务。

## 4. 原始证据与核对

任务运行期间按 `config/common/m6_rosbag_qos.yaml` 录制既有 M6 Topic。结束后核对：

- JSONL 的任务 ID、反馈阶段、终态和错误码与 Action 输出一致；
- 一秒桶与 rosbag 中对应时间窗的 `odom`、`pose`、`scan`、安全状态一致；
- 缺失 Topic 和时间倒退被标为数据质量无效；
- 文件哈希、Git提交号、运行配置和 rosbag 路径写入证据清单。

仓库中的 `samples/w3_synthetic_fixture.jsonl` 只用于格式测试，不是正式仿真证据。
