# M1 ROS 2公共接口规范

> 版本：m1.v2（M6兼容扩展）
> 状态：已确认
> 适用范围：M2～G2的ROS 2机器人部分
> 技术基线：Ubuntu 22.04、ROS 2 Humble
> 边界：本文定义Topic、Service、Action、消息、命名和参数规则；QoS、时间与TF细则见
> `M1_QoS时间与TF规范.md`。

## 1. 目标

本规范为仿真和实体机器人提供一致的ROS 2公共接口。上层节点不得根据`sim`或`real`
改变接口名称、消息类型或行为语义，只能通过启动参数、驱动适配器和配置文件切换底层实现。

本文中的“公共接口”指允许跨软件包、跨子系统或由测试程序调用的接口。节点内部实现细节
应使用私有名称，不纳入公共契约。

机器可读清单位于`../config/common/interface_contract.yaml`。文档与清单不一致时视为
契约检查失败，必须在同一变更中修正。

## 2. 通用原则

1. 数据流、连续状态和事件使用Topic；
2. 应在短时间内完成、无需持续反馈的请求使用Service；
3. 持续时间不确定、需要反馈、取消、超时和结果的任务使用Action；
4. 优先复用ROS 2标准消息，不为改名或封装单一字段创建自定义消息；
5. 自定义接口只能放入后续`robot_interfaces`软件包，并必须记录版本、错误码和契约测试；
6. 仿真和实体实现必须提供相同的公共名称、类型和语义；
7. 公共接口不得包含`sim`、`real`、具体硬件品牌或Gazebo版本；
8. 节点源码使用相对名称，由Launch统一应用机器人命名空间；
9. M0示例接口`/m0/cpp_status`和`/m0/py_status`不属于正式机器人接口；
10. AI Agent在G2通过前不接入本文接口，G2后也只能调用冻结的白名单能力。

## 3. 命名规则

### 3.1 机器人命名空间

- Launch参数名：`robot_namespace`；
- 默认值：`robot`；
- 单机器人解析后公共前缀：`/robot`；
- 多机器人示例：`/robot_01`、`/robot_02`；
- `/tf`、`/tf_static`和`/clock`的命名及多机器人处理在W5定义。

节点代码不得硬编码`/robot`。例如源码发布`scan`，由命名空间解析为`/robot/scan`。

### 3.2 名称格式

- 节点、Topic、Service、Action、参数和Frame使用小写`snake_case`；
- 名称使用名词或明确动宾结构，不使用难以理解的缩写；
- Topic不使用`get_`、`set_`等Service式名称；
- Service使用明确动作，例如`save_map`、`clear_faults`；
- Action使用目标能力名称，例如`navigate_to_pose`；
- 不使用连续编号表达语义，例如`sensor1`、`sensor2`；
- 不在名称中编码消息类型，例如`scan_laserscan`；
- 不用重映射掩盖同一接口的类型冲突。

### 3.3 节点名称

正式节点的建议基础名称如下：

| 对象 | 节点基础名称 |
|---|---|
| 模型与状态发布 | `robot_state_publisher` |
| 底盘驱动或适配 | `base_driver` |
| 雷达驱动或适配 | `lidar_driver` |
| 相机驱动或适配 | `camera_driver` |
| IMU驱动或适配 | `imu_driver` |
| 状态估计 | `state_estimator` |
| SLAM | `slam` |
| 定位 | `localization` |
| 导航能力适配 | `navigation` |
| 人员感知 | `person_detector` |
| 安全监督 | `safety_supervisor` |
| 非AI任务管理 | `task_manager` |

第三方节点可保留上游可识别名称，但必须通过命名空间和适配层满足公共接口，不直接修改
第三方源码只为改变名称。

## 4. Topic公共接口

表中名称为默认命名空间解析后的名称。实现代码应优先使用相对名称。

### 4.1 基础运动与状态

| 名称 | 消息类型 | 发布方 | 订阅方 | 语义与约束 | 状态 |
|---|---|---|---|---|---|
| `/robot/cmd_vel` | `geometry_msgs/msg/Twist` | 安全监督或命令仲裁节点 | 底盘驱动/控制器 | 发送给底盘的最终受控速度；其他节点不得绕过安全链直接发布 | 设计确认 |
| `/robot/odom` | `nav_msgs/msg/Odometry` | 底盘里程计或状态估计唯一发布者 | 定位、导航、诊断和测试 | 连续局部里程计；发布责任在W5进一步冻结 | 设计确认 |
| `/robot/joint_states` | `sensor_msgs/msg/JointState` | `joint_state_broadcaster`或实体适配器 | 状态发布、诊断和测试 | 仿真与实体使用相同关节名称 | 设计确认 |
| `/robot/battery_state` | `sensor_msgs/msg/BatteryState` | 实体电源适配器或仿真状态节点 | 安全、任务和诊断 | M1不要求实体电池品牌 | 设计确认 |

导航、遥控和测试程序产生的未仲裁速度属于内部接口，不纳入公共契约。安全监督节点负责
选择合法来源并只向`cmd_vel`发布最终命令。

### 4.2 传感器

| 名称 | 消息类型 | 发布方 | 订阅方 | 语义与约束 | 状态 |
|---|---|---|---|---|---|
| `/robot/scan` | `sensor_msgs/msg/LaserScan` | 雷达驱动/适配器 | SLAM、定位、导航和测试 | 标准二维激光扫描 | 设计确认 |
| `/robot/imu/data` | `sensor_msgs/msg/Imu` | IMU驱动/适配器 | 状态估计、诊断和测试 | 单位、方向和协方差在W5定义 | 设计确认 |
| `/robot/camera/color/image_raw` | `sensor_msgs/msg/Image` | 相机驱动/适配器 | 图像处理、感知和测试 | 未压缩原始彩色图像 | 设计确认 |
| `/robot/camera/color/camera_info` | `sensor_msgs/msg/CameraInfo` | 相机驱动/适配器 | 图像处理、感知和测试 | 必须与对应图像使用一致标定 | 设计确认 |
| `/robot/camera/depth/image_raw` | `sensor_msgs/msg/Image` | 深度相机驱动/适配器 | 感知和测试 | 只有选用深度相机时启用 | 条件接口 |
| `/robot/camera/depth/camera_info` | `sensor_msgs/msg/CameraInfo` | 深度相机驱动/适配器 | 感知和测试 | 与深度图像成对出现 | 条件接口 |

压缩图像由`image_transport`生成派生接口，不作为替代原始图像的唯一公共接口。

### 4.3 地图、定位、诊断与安全

| 名称 | 消息类型 | 发布方 | 订阅方 | 语义与约束 | 状态 |
|---|---|---|---|---|---|
| `/robot/map` | `nav_msgs/msg/OccupancyGrid` | SLAM或地图服务唯一发布者 | 定位、导航、可视化和测试 | 地图来源由运行模式选择，不并行发布 | 设计确认 |
| `/robot/initialpose` | `geometry_msgs/msg/PoseWithCovarianceStamped` | RViz2、测试或受控界面 | 定位节点 | 仅用于已知地图中的初始位姿输入 | 设计确认 |
| `/robot/pose` | `geometry_msgs/msg/PoseWithCovarianceStamped` | 定位能力适配器 | 任务、诊断和测试 | 项目统一全局位姿输出；不得替代TF | 设计确认 |
| `/robot/diagnostics` | `diagnostic_msgs/msg/DiagnosticArray` | 各节点或诊断聚合器 | 运维、安全和测试 | 汇总设备、节点和接口健康状态 | 设计确认 |
| `/robot/safety/stop_active` | `std_msgs/msg/Bool` | 安全监督唯一发布者 | 底盘、任务、诊断和测试 | `true`表示禁止继续运动；原因同时写入诊断 | 设计确认 |

`stop_active`是软件安全状态，不替代实体急停回路、MCU保护或硬件失联停车。

## 5. Service公共接口

| 名称 | Service类型 | 服务端 | 语义与约束 | 状态 |
|---|---|---|---|---|
| `/robot/map/save_map` | `nav2_msgs/srv/SaveMap` | 地图保存能力适配器 | 保存当前地图；文件位置必须经过参数约束 | 接口已验证 |
| `/robot/safety/clear_faults` | `std_srvs/srv/Trigger` | 安全监督 | 只清除允许软件恢复的故障；急停或硬件故障未解除时必须拒绝 | 设计确认 |

Service回调不得执行长时间阻塞工作。地图保存若无法在明确超时内完成，应由能力适配器
提供Action或异步状态，而不是无限阻塞Service。

生命周期节点使用ROS 2标准生命周期Service，但这些管理接口不作为普通业务能力暴露。

## 6. Action公共接口

| 名称 | Action类型 | 服务端 | 语义与约束 | 状态 |
|---|---|---|---|---|
| `/robot/navigation/navigate_to_pose` | `nav2_msgs/action/NavigateToPose` | Nav2或导航能力适配器 | 导航到经过验证的目标位姿，支持反馈、取消、超时和失败 | 接口已验证 |
| `/robot/navigation/follow_waypoints` | `nav2_msgs/action/FollowWaypoints` | Nav2或导航能力适配器 | 顺序执行受约束的位姿列表 | 接口已验证 |
| `/robot/task/execute` | `robot_interfaces/action/ExecuteRobotTask` | 非AI任务管理器 | 执行结构化导航并采集基础感知任务，支持反馈、取消、总超时和稳定错误码 | 接口已验证 |

Action取消使用ROS 2 Action协议，不额外创建同名“取消”Service。M1不定义自然语言地点接口，
语义地点到物理位姿的转换属于G2之后的AI—ROS 2接口层。

### 6.1 M6结构化任务契约

`ExecuteRobotTask`只接受`NAVIGATE_AND_SENSE`任务，目标必须包含唯一任务ID、`map`坐标系中的
有限且合法位姿、基础感知模式和`10～300 s`总超时。任务管理器同时只允许一个活动目标，执行
中收到的第二个目标以`BUSY`拒绝，不隐式并行或抢占。

反馈阶段为`ACCEPTED → VALIDATING → NAVIGATING → SENSING`；取消可从任一执行阶段进入
`CANCELING`。终态只有`SUCCEEDED`、`FAILED`和`CANCELED`，终态不得保留下游活动目标。
安全停车优先级高于用户取消、任务超时、导航失败和感知失败。

结果使用`SensorSnapshot`表达雷达、RGB图像和全局位姿的可用性与基础元数据，不表达目标类别、
人员检测或其他语义结论。完整状态迁移、错误码和时间门限由
`config/common/m6_task_contract.yaml`机器可读契约冻结。

## 7. 暂缓定义的接口

以下接口需要更多Schema、错误码或能力边界设计，本轮不使用临时消息冻结：

| 能力 | 暂缓原因 | 后续入口 |
|---|---|---|
| 标准化人员检测结果 | 标准消息、边界框、类别和置信度Schema尚未确定 | 人员感知资源确认后设计 |
| 机器人综合状态 | 需要统一运行、安全、定位、电量和任务状态 | G2能力接口冻结前设计 |
| 安全详细状态 | `Bool`只能表达停车激活，详细原因需稳定错误码 | 安全对象设计时补充 |

暂缓项不得使用`std_msgs/String`承载未定义JSON，也不得通过话题名称变化模拟版本管理。

## 8. 参数规范

### 8.1 声明与加载

- 所有正式参数必须由节点显式声明；
- 默认参数放在软件包或`config/common/`，模式差异放在`config/sim/`和`config/real/`；
- 公共参数名称在仿真和实体间保持一致，取值可以不同；
- Launch只负责组合、命名空间、模式选择和配置文件加载，不复制整套参数；
- 未声明参数、拼写错误参数和类型不匹配必须导致明确失败；
- 密钥、令牌、Wi-Fi和设备凭据不得写入参数文件或Git。

### 8.2 命名与类型

- 参数使用小写`snake_case`；
- 布尔参数使用`enable_*`、`publish_*`或明确状态词；
- 时间参数以后缀`_sec`或`_ms`标明单位；
- 频率参数以后缀`_hz`标明单位；
- 距离、速度和角度参数分别使用`_m`、`_mps`、`_rad`等SI单位后缀；
- Frame参数以后缀`_frame`或`_frame_id`表示；
- Topic参数以后缀`_topic`表示，并优先使用相对名称；
- 枚举型字符串必须列出允许值，不能接受任意文本。

### 8.3 公共启动参数

| 参数 | 类型 | 默认值 | 作用 |
|---|---|---|---|
| `robot_namespace` | string | `robot` | 设置机器人公共命名空间 |
| `mode` | string | `sim` | 只允许`sim`或`real` |
| `use_sim_time` | bool | `true`（sim）/`false`（real） | 时间行为细则在W5冻结 |
| `params_file` | string | 模式默认文件 | 加载当前组合的参数文件 |

`mode`只选择底层实现和配置，不得改变公共接口名称、类型或语义。

## 9. 接口版本与变更

- W4首版接口版本标识为`m1.v1`；M6-W2增加结构化任务Action和感知快照后提升为兼容扩展
  `m1.v2`，原有Topic、Service、Action的名称、类型和语义均不改变；
- 文档审查通过后，名称和类型变更必须记录原因、兼容性和迁移方法；
- M2～M6可以补充接口，但不能静默改变已使用接口的消息类型或语义；
- 破坏性变更必须提升接口版本，并同步更新矩阵、配置、契约测试和回归测试；
- G1冻结仿真—实体公共接口；
- G2冻结AI可调用的机器人能力接口；
- 接口版本不得通过Topic名称后缀随意增加`_v2`，除非迁移期确需并行兼容。

## 10. 验证状态与后续工作

本机已确认以下基础消息可由ROS 2 Humble解析：

- `geometry_msgs/msg/Twist`、`geometry_msgs/msg/TwistStamped`；
- `nav_msgs/msg/Odometry`；
- `sensor_msgs/msg/LaserScan`、`Imu`、`Image`和`CameraInfo`；
- `diagnostic_msgs/msg/DiagnosticArray`；
- `std_srvs/srv/Trigger`。

2026年7月31日使用Ubuntu 22.04软件源中的`ros-humble-nav2-msgs 1.1.20`验证：
`NavigateToPose`、`FollowWaypoints`和`SaveMap`均可由ROS 2 Humble正确解析，契约中的
接口类型名称与实际定义一致。验证采用官方Debian包的隔离解包前缀，不代表该包已安装到
系统环境。当前机器契约检查验证接口名称、类型字符串和结构，但不替代真实Nav2运行验证；
M2开始Nav2集成前，必须在软件包依赖、开发环境和CI中声明并安装`ros-humble-nav2-msgs`。
详细证据见`memo/M1_W4接口依赖验证_2026-07-31.md`。

W5已经在`M1_QoS时间与TF规范.md`中定义：

- 各Topic的QoS策略；
- 时间戳、`/clock`和`use_sim_time`规则；
- `map → odom → base_link → sensor_link`发布责任；
- Frame命名、单位、坐标方向、频率和超时要求。

W6已为本文公共接口建立静态机器契约检查。接口频率、超时、QoS兼容、TF唯一发布者和
时间跳变等运行时契约，将在M2以后随真实节点实现逐步加入自动测试。

用户于2026年7月30日确认`m1.v1`进入M1正式基线。M2～M5保持该接口兼容；2026年8月12日
M6-W2新增`/robot/task/execute`和`SensorSnapshot`，形成兼容扩展`m1.v2`。新增接口已在M6-W3
完成服务端发现、目标校验、结果、取消、并发拒绝和诊断黑盒验证；导航与感知编排
仍须分别通过M6-W4和W5运行验证。
