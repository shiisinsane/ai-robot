# W7 B2资格Pilot进度

> 日期：2026-08-28
> 授权范围：15项GUI资格Pilot，不含360项正式采集
> 当前进度：15/15通过；资格Pilot完成，等待B2正式预注册评审

| 序号 | 路线 | 障碍 | 自动证据 | GUI确认 | 结论 |
|---:|---|---|---|---|---|
| 1 | `horizontal_center` | none | `retry-002`为`valid_success`，快照、rosbag、清理通过 | 用户于2026-08-28确认运动正常，无碰撞、异常跳动、持续旋转或卡住 | 通过 |
| 2 | `horizontal_center` | low | `retry-005`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留；`retry-004`亦为`return_code=0` | 用户于2026-08-28确认`retry-005` GUI运动正常 | 通过 |
| 3 | `horizontal_center` | medium | `attempt-002`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-28确认GUI运动正常 | 通过 |
| 4 | `vertical_center` | none | `attempt-001`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-28确认GUI验证无误 | 通过 |
| 5 | `vertical_center` | low | `attempt-002`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-31确认GUI验证无误 | 通过 |
| 6 | `vertical_center` | medium | `attempt-001`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-31确认GUI验证无误 | 通过 |
| 7 | `diagonal_rising` | none | 修复路线后的`attempt-002`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-31确认GUI验证无误 | 通过 |
| 8 | `diagonal_rising` | low | `attempt-001`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-31确认GUI验证无误 | 通过 |
| 9 | `diagonal_rising` | medium | `attempt-001`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-31确认GUI验证无误 | 通过 |
| 10 | `diagonal_falling` | none | `attempt-001`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-31确认GUI验证无误 | 通过 |
| 11 | `diagonal_falling` | low | `attempt-001`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-31确认GUI验证无误 | 通过 |
| 12 | `diagonal_falling` | medium | `attempt-001`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-31确认GUI验证无误 | 通过 |
| 13 | `horizontal_offset` | none | `attempt-001`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-31确认GUI验证无误 | 通过 |
| 14 | `horizontal_offset` | low | `attempt-001`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-31确认GUI验证无误 | 通过 |
| 15 | `horizontal_offset` | medium | `attempt-001`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-31确认GUI验证无误 | 通过 |

说明：首次尝试在发送任务前因资格计划缺少兼容字段`repetition`退出，残留检查通过；`retry-001`
自动证据通过但用户未观察GUI；两次均保留，不覆盖。正式资格结论采用`retry-002`。

第2项首次资格运行曾出现定位不连续和恢复行为，因此没有用动作最终成功替代GUI运动合理性门禁。
后续重跑中，`retry-002`在任务下发前因采集快照时间不一致退出，`retry-003`在环境Ready前因
`planner_server/change_state`响应超时退出；二者均属于无效运行，不计资格结果，且清理无残留。
采集快照一致性问题修正后，`retry-004`与`retry-005`连续返回成功；正式资格结论采用同时具备
自动有效样本、无残留证据和用户GUI确认的`retry-005`。第3项有效运行尚未完成。

第3项`attempt-001`已启动环境，但在任务下发前退出：生命周期查询期间收到更新的odom，随后使用
查询前的旧仿真时钟计算消息年龄，产生`age=-0.776`。该取时顺序已修正且相关测试`15 passed`；
本轮不计资格失败，保留为无效运行证据；修正后使用`attempt-002`完成有效重跑。

第3项正式资格结论采用`attempt-002`：自动样本、动作终态、运行返回码、清理证据与用户GUI确认
一致。

第4项正式资格结论采用`attempt-001`，自动证据与用户GUI确认一致。

第5项`attempt-001`自动证据为`valid_success`且清理无残留，但用户未完成GUI观察，因此不作为
正式资格结论。正式资格结论采用`attempt-002`：自动样本、动作终态、运行返回码、清理证据与
用户GUI确认一致。

第6项正式资格结论采用`attempt-001`，自动样本、动作终态、运行返回码、清理证据与用户GUI确认
一致。

第7项`attempt-001`中，用户在GUI确认机器人出生状态与圆柱形障碍重叠。运行证据显示临时障碍
已正确移至`(8.0, 8.0)`、机器人出生位姿为`(-1.8, -1.5)`，且本轮清理无残留；世界文件中的
固定圆柱地标`landmark_b`位于`(-1.6, -1.2)`、半径`0.3 m`，与机器人出生包络冲突。因此该轮
判定为路线设计缺陷证据，不计业务任务失败或资格结果；第7项及后续资格执行暂停。

静态设计随后补充机器人包络与固定世界模型的整段路线碰撞门禁，并将`diagonal_rising`修复为
`(-2.2,-0.6) → (2.2,0.6)`。第7项正式资格结论采用修复后的`attempt-002`，自动样本、动作
终态、运行返回码、清理证据与用户GUI确认一致。

第8项正式资格结论采用`attempt-001`，自动样本、动作终态、运行返回码、清理证据与用户GUI确认
一致。

第9项正式资格结论采用`attempt-001`，自动样本、动作终态、运行返回码、清理证据与用户GUI确认
一致。

第10项正式资格结论采用`attempt-001`，自动样本、动作终态、运行返回码、清理证据与用户GUI确认
一致。

第11项正式资格结论采用`attempt-001`，自动样本、动作终态、运行返回码、清理证据与用户GUI确认
一致。

第12项正式资格结论采用`attempt-001`，自动样本、动作终态、运行返回码、清理证据与用户GUI确认
一致。

第13项正式资格结论采用`attempt-001`，自动样本、动作终态、运行返回码、清理证据与用户GUI确认
一致。

第14项正式资格结论采用`attempt-001`，自动样本、动作终态、运行返回码、清理证据与用户GUI确认
一致。

第15项正式资格结论采用`attempt-001`，自动样本、动作终态、运行返回码、清理证据与用户GUI确认
一致。15项正式证据经汇总复核全部为`valid_success`，且每项进程组残留检查均通过。资格Pilot
完成不等于B2正式采集获批；360项候选计划仍未预注册、未授权、未执行。
