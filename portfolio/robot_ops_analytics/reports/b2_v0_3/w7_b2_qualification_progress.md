# W7 B2资格Pilot进度

> 日期：2026-08-28
> 授权范围：15项GUI资格Pilot，不含360项正式采集
> 当前进度：4/15通过；等待用户确认是否进入第5项

| 序号 | 路线 | 障碍 | 自动证据 | GUI确认 | 结论 |
|---:|---|---|---|---|---|
| 1 | `horizontal_center` | none | `retry-002`为`valid_success`，快照、rosbag、清理通过 | 用户于2026-08-28确认运动正常，无碰撞、异常跳动、持续旋转或卡住 | 通过 |
| 2 | `horizontal_center` | low | `retry-005`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留；`retry-004`亦为`return_code=0` | 用户于2026-08-28确认`retry-005` GUI运动正常 | 通过 |
| 3 | `horizontal_center` | medium | `attempt-002`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-28确认GUI运动正常 | 通过 |
| 4 | `vertical_center` | none | `attempt-001`为`valid_success`，终态`success=true`、`error_code=0`，清理无残留 | 用户于2026-08-28确认GUI验证无误 | 通过 |

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

第4项正式资格结论采用`attempt-001`，自动证据与用户GUI确认一致。第5项尚未启动。
