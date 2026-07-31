# 测试基线

## 测试层级

| 目录 | 用途 | 当前最小样例 |
|---|---|---|
| `unit/` | 不启动ROS图的普通逻辑单元测试 | 契约验证器成功与失败分支 |
| `node/` | 单节点或少量节点的接口行为 | 显式QoS的Publisher/Subscriber通信 |
| `contract/` | 名称、类型、QoS、时间、TF及安全约束 | `interface_contract.yaml`检查 |
| `integration/` | Launch和多组件组合 | 启动并安全停止Python示例节点 |
| `simulation/` | 仿真时钟、TF、故障注入和场景 | `use_sim_time`与唯一`/clock`策略 |
| `real/` | G1后的实体与安全测试 | 当前仅保留人工安全要求 |

## 命名与结构

- 测试文件使用`test_<对象>_<行为>.py`；
- 测试函数使用`test_<前置条件>_<预期结果>()`；
- 可复用输入放入`test_data/`，不得在测试代码中嵌入大型数据；
- 每项测试只验证一个清晰行为，失败信息必须指出接口、规则或场景；
- 需要ROS图的测试使用独立`ROS_DOMAIN_ID`，避免本机其他节点污染结果；
- 单元和契约测试不得依赖网络、图形界面或实体设备；
- 实体测试不得进入默认自动测试入口。

## 统一执行

```bash
bash scripts/build.sh
bash scripts/test.sh
```

`scripts/test.sh`先执行各ROS 2软件包内的C++/Python测试，再执行本目录中的仓库级pytest。
也可以单独检查机器契约：

```bash
python3 scripts/check_interface_contract.py
```

## 结果与失败证据

每次正式验证至少记录：

- 测试名称、命令、开始和结束时间；
- 操作系统、ROS发行版、RMW实现和关键依赖版本；
- Git提交号、接口契约版本和配置文件；
- 通过、失败或跳过数量；
- 失败断言、节点日志、退出码和相关Topic/TF状态；
- 使用的`ROS_DOMAIN_ID`及人工检查项。

构建产物和普通运行日志保留在被Git忽略的`build/`、`install/`、`log/`。需要纳入阶段证据
的摘要和索引进入`docs/`；rosbag和大型原始数据的保存规则由M1-W7定义。
