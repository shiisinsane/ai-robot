# M1 QoS、时间与TF规范

> 版本：M1-W5首版
> 状态：已确认
> 适用范围：M2～G2的ROS 2机器人部分
> 技术基线：Ubuntu 22.04、ROS 2 Humble
> 关联契约：`../config/common/interface_contract.yaml`

## 1. 目标与边界

本文在M1-W4公共接口基础上定义QoS、消息时间、仿真时间、频率、超时和TF责任。
仿真与实体实现必须遵守同一组公共契约；允许根据设备能力提高发布频率，但不得降低最低
频率、放宽安全超时或静默改变QoS。

本文的频率和超时是M2以后实现及测试的准入基线，不表示M1已经实现对应机器人能力。
具体设备采样率、导航参数和性能指标在各后续里程碑中通过实测收紧。

## 2. QoS通用规则

### 2.1 策略

1. 所有公共Topic显式设置QoS，不依赖RMW厂商默认值；
2. 高频传感器数据使用`best_effort + volatile`，优先获得最新样本；
3. 控制、状态、诊断和位姿使用`reliable`；
4. 地图和安全停车状态使用`transient_local`，使晚加入订阅者获得最近状态；
5. 所有公共Topic使用`keep_last`和有界队列，不使用无界`keep_all`；
6. Publisher和Subscriber必须满足ROS 2 Request/Offered兼容关系；
7. 发现不兼容QoS必须写入诊断并使契约测试失败，不得静默收不到数据；
8. Service保持ROS 2服务默认的`reliable + volatile`，避免服务重启后处理陈旧请求；
9. Action使用ROS 2 Action默认QoS；业务超时由Action客户端和任务管理器显式控制；
10. `deadline`、`lifespan`和`liveliness_lease_duration`在首版DDS契约中保持未指定，
    频率和失联由节点监控实现，避免不同RMW或第三方节点产生兼容性问题。

### 2.2 QoS配置档

| 配置档 | History/Depth | Reliability | Durability | 用途 |
|---|---|---|---|---|
| `control` | `keep_last/1` | `reliable` | `volatile` | 最终速度命令 |
| `state_stream` | `keep_last/10` | `reliable` | `volatile` | 里程计、关节和连续位姿 |
| `sensor_stream` | `keep_last/5` | `best_effort` | `volatile` | 雷达、图像和一般传感器 |
| `imu_stream` | `keep_last/20` | `best_effort` | `volatile` | 高频IMU |
| `latched_state` | `keep_last/1` | `reliable` | `transient_local` | 地图、标定、安全状态 |
| `event_input` | `keep_last/10` | `reliable` | `volatile` | 初始位姿等操作输入 |
| `diagnostics` | `keep_last/10` | `reliable` | `volatile` | 聚合诊断 |

### 2.3 Topic契约

| Topic | QoS配置档 | 最低/期望频率 | 陈旧或超时判定 |
|---|---|---|---|
| `/robot/cmd_vel` | `control` | 按需，运动时持续发布 | 超过`0.2 s`无合法命令必须输出零速度并停车 |
| `/robot/odom` | `state_stream` | 最低`20 Hz` | 超过`0.2 s`无更新视为失效，禁止继续自主运动 |
| `/robot/joint_states` | `state_stream` | 最低`20 Hz` | 超过`0.5 s`标记陈旧 |
| `/robot/battery_state` | `latched_state` | 最低`1 Hz` | 超过`5.0 s`标记陈旧；实体安全策略可更严格 |
| `/robot/scan` | `sensor_stream` | 最低`10 Hz` | 超过`0.5 s`标记失效 |
| `/robot/imu/data` | `imu_stream` | 最低`50 Hz` | 超过`0.2 s`标记失效 |
| 彩色及深度`image_raw` | `sensor_stream` | 最低`15 Hz` | 超过`0.5 s`标记失效 |
| 彩色及深度`camera_info` | `sensor_stream` | 与对应图像同频发布 | 超过`0.5 s`标记失效，且必须与图像匹配 |
| `/robot/map` | `latched_state` | 事件驱动；建图时按实现更新 | 导航启动前必须存在有效地图 |
| `/robot/initialpose` | `event_input` | 事件驱动 | 不作流超时；定位节点校验时间戳 |
| `/robot/pose` | `state_stream` | 最低`10 Hz` | 超过`0.5 s`标记定位输出失效 |
| `/robot/diagnostics` | `diagnostics` | 最低`1 Hz`或状态变化时立即发布 | 超过`5.0 s`标记诊断源失联 |
| `/robot/safety/stop_active` | `latched_state` | 最低`10 Hz`并在变化时立即发布 | 超过`0.3 s`无状态按停车激活处理 |

频率验证允许启动和生命周期切换的明确宽限期。宽限期必须写入测试配置，不得掩盖运行期
断流。条件深度相机接口未启用时不执行频率检查，但启用后必须满足同一契约。

## 3. 时间与时间戳

### 3.1 时钟来源

- 仿真模式：所有ROS 2节点必须设置`use_sim_time: true`，唯一权威时间来自全局`/clock`；
- 实体模式：所有ROS 2节点必须设置`use_sim_time: false`，使用系统ROS时间；
- 同一运行图中禁止一部分节点使用仿真时间、另一部分节点使用系统时间；
- `/clock`不放入`/robot`命名空间，单ROS域只能有一个权威发布者；
- Fortress通过`ros_gz_bridge`桥接`/clock`，QoS使用
  `keep_last/1 + best_effort + volatile`；
- 仿真暂停时ROS时间允许停止，监控程序不得仅靠ROS时间判断进程失联，应同时使用稳态时钟；
- 自动测试使用独立`ROS_DOMAIN_ID`，避免其他仿真实例的`/clock`或TF污染。

### 3.2 消息时间戳

1. 带`std_msgs/Header`的传感器消息使用数据采样时刻，不使用处理完成或发布时刻；
2. `Odometry`和位姿消息使用状态估计所代表的时刻；
3. 同一图像与`CameraInfo`必须具有相同或可明确关联的采样时间和Frame；
4. 所有时间戳必须来自当前模式的权威ROS时钟，不得混入Unix时间、设备启动时间或另一时钟域；
5. 驱动收到设备时间时必须先转换到ROS时钟，并记录同步方法和最大误差；
6. 时间戳为零、明显来自未来或早于当前缓存窗口的数据必须拒绝或标记诊断；
7. `/robot/cmd_vel`当前类型为无Header的`Twist`，安全监督以本地稳态时钟记录接收时间；
8. TF时间戳必须与产生该位姿的数据时间一致，不能统一改写成“当前时间”掩盖延迟。

### 3.3 时间跳变

仿真重置、rosbag回放或`/clock`重新连接可能导致时间前跳或后跳。检测到后跳或超过测试
阈值的大幅前跳时，状态估计、TF缓存、同步器、控制超时和任务计时器必须重置或进入安全
停止；不得继续使用跳变前的速度命令、传感器缓存或导航目标计时。

业务超时使用ROS时间还是稳态时间必须明确：

- 数据时间一致性、仿真场景时长和rosbag回放使用ROS时间；
- 命令失联、安全看门狗、进程健康和外部通信超时使用稳态时间；
- Action执行超时默认使用稳态时间，同时记录对应ROS时间用于回放分析。

## 4. 坐标系与单位

### 4.1 坐标约定

- 遵守REP-103，长度用米、时间用秒、角度用弧度；
- 机体坐标采用右手系：`x`向前、`y`向左、`z`向上；
- 正偏航角绕`z`轴逆时针，四元数是姿态的首选表达；
- Frame ID使用小写`snake_case`，不得以`/`开头；
- 单机器人基础Frame固定为`map`、`odom`、`base_link`及语义明确的传感器Frame；
- 传感器Frame示例：`laser_link`、`imu_link`、`camera_color_optical_frame`；
- 相机光学Frame遵循`z`向前、`x`向右、`y`向下的光学坐标约定；
- 不得在仿真和实体模式中改变公共Frame名称或轴方向。

### 4.2 TF树与发布责任

```text
map
└── odom
    └── base_link
        ├── laser_link
        ├── imu_link
        └── camera_link
            └── camera_color_optical_frame
```

| Transform | 类型 | 唯一发布责任 | 最低频率/有效性 |
|---|---|---|---|
| `map → odom` | 动态 | 当前激活的SLAM或定位节点二选一 | 最低`5 Hz`，超过`1.0 s`无更新视为全局定位失效 |
| `odom → base_link` | 动态 | 状态估计节点；未启用融合时可由底盘里程计发布，但不得并存 | 最低`20 Hz`，超过`0.2 s`无更新视为局部状态失效 |
| `base_link → sensor_link` | 静态 | `robot_state_publisher`根据URDF/Xacro发布 | 启动后可被晚加入者立即取得 |
| 固定本体Link | 静态 | `robot_state_publisher` | 通过`/tf_static`发布一次并持久可用 |
| 可动关节Link | 动态 | `robot_state_publisher`根据`joint_states`发布 | 不低于关节状态有效更新频率 |

同一父子Frame只能有一个权威发布者。SLAM和定位不得同时发布`map → odom`；状态估计与
底盘控制器不得同时发布`odom → base_link`。切换发布者必须通过生命周期或Launch组合保证
旧发布者已经停止。

### 4.3 `/tf`、`/tf_static`与多机器人

- 动态变换发布到全局`/tf`，QoS为`keep_last/100 + reliable + volatile`；
- 静态变换发布到全局`/tf_static`，QoS为
  `keep_last/1 + reliable + transient_local`；
- 节点不得通过私有Topic发布另一棵不可见TF树；
- 单机器人阶段不为Frame增加`robot`前缀；
- 多机器人共用ROS域前，必须设计唯一Frame前缀，例如`robot_01/base_link`，并通过
  契约测试确认Nav2、RViz2、rosbag和桥接兼容；不得只给Topic加命名空间而复用相同Frame；
- 未完成多机器人Frame前缀验证前，多个机器人应使用不同`ROS_DOMAIN_ID`隔离。

## 5. 故障处理

- 任何安全关键数据或TF超过超时后，安全监督进入停车状态；
- 恢复数据流不会自动清除急停或硬件故障，必须满足对应恢复条件；
- QoS不兼容、重复TF发布者、时间域混用、未来时间戳和TF断链均至少产生`ERROR`诊断；
- 地图、定位或传感器无效时拒绝启动依赖它们的Action，不得带故障降级继续导航；
- 诊断必须包含接口或Frame、首次发生时间、最近有效时间和处置状态。

## 6. W6契约测试入口

W6至少自动检查：

1. 机器契约可解析，所有Topic均引用已定义QoS配置档；
2. 仿真和实体的接口名称、类型、QoS和Frame一致；
3. Publisher与Subscriber QoS兼容；
4. 启用接口达到最低频率，断流后在规定时间内产生故障；
5. 消息时间戳非零、不过度超前且Frame正确；
6. TF树连通、父子关系正确、无重复发布者并达到最低频率；
7. `/tf_static`和地图可被晚加入订阅者取得；
8. 仿真节点全部使用`use_sim_time: true`且只存在一个`/clock`权威来源；
9. 时间跳变后旧缓存和速度命令不会继续生效；
10. 安全状态断流按停车激活处理。

## 7. 参考依据

- ROS 2 Humble QoS设置：
  <https://docs.ros.org/en/humble/Concepts/Intermediate/About-Quality-of-Service-Settings.html>
- REP-103单位与坐标约定：<https://www.ros.org/reps/rep-0103.html>
- REP-105移动机器人坐标系：<https://www.ros.org/reps/rep-0105.html>

用户于2026年7月31日确认本方案。M1-W5已完成，W6和W7随后完成，当前工作入口为
M1-W8正式验收。第6节中的运行时检查项将在M2以后随真实节点实现逐步落地。
