# 求职表述证据索引

> 用途：确保简历、作品集和面试中的每项数字都能追溯。此文件是求职导航，不替代正式报告。

| 对外表述 | 证据 | 准入状态 |
|---|---|---|
| 独立构建运营指标体系 | `reports/common/metric_tree.md`、`schemas/common/metric_dictionary.yaml`、`reports/common/metric_definition_review.md` | 可用 |
| 设计任务、事件、遥测和实验维度模型 | `schemas/common/warehouse.sql`、`schemas/common/data_dictionary.yaml`、`reports/common/data_lineage.md` | 可用 |
| 处理32,866条原始记录 | `reports/acceptance/w6_acceptance_20260828.md`、`resume_evidence_map.md` | 可用 |
| 形成45项任务、9,725条事件、1,759个遥测桶 | `reports/b1_v0_2/w6_b1_sql_reconciliation.md`、`resume_evidence_map.md` | 可用 |
| 建立21条质量规则并隔离7次无效尝试 | `reports/acceptance/w6_acceptance_20260828.md`、`resume_evidence_map.md` | 可用 |
| 39项SQL/Python结果一致 | `reports/b1_v0_2/w6_b1_sql_reconciliation.md` | 可用 |
| 45次预注册平衡区组实验 | `reports/b1_v0_2/w6_b1_preregistration.md`、`reports/b1_v0_2/w6_b1_statistical_analysis.md` | 可用 |
| low使周期中位数增加21.511秒 | `reports/b1_v0_2/w6_b1_statistical_analysis.md` | 可用 |
| medium使周期中位数增加27.165秒 | `reports/b1_v0_2/w6_b1_statistical_analysis.md` | 可用 |
| 三组15/15成功、遥测覆盖100%、安全停车为0 | `reports/acceptance/w6_business_analysis.md` | 可用，但必须注明仿真和样本数 |
| 失败预测模型PR-AUC、召回率 | 尚无独立测试报告 | 禁止使用 |
| 策略改善生产效率或成本 | 尚无实体/生产对照实验 | 禁止使用 |
| 固定阈值误报、分档预算、容量和改道决策 | 待完成仿真情景分析 | 目前只能作为下一阶段目标 |

## 指标体系的个人工作证据

- 指标树包含北极星、完成能力、周转效率、诊断和安全/质量护栏。
- 指标字典记录业务含义、统计实体、公式、单位、窗口、过滤条件、维度、空值政策及限制。
- 关键口径明确分离拒绝、取消、失败和故障注入，防止人为美化完成率。
- 机器人有效运行时间先合并重叠区间，再作为北极星指标分母，避免重复计算机器人小时。
- 正式耗时使用ROS仿真时间；墙钟仅作环境诊断。
- SLA没有凭空填写，而是等待基线形成后再冻结。

## 对外陈述边界

- 必须说明数据来自ROS 2/Gazebo受控仿真。
- 旧版81项探索和A1 30项实验只用于问题发现及混杂审计。
- B1 45项正式实验支持周期与绕行结论，不支持失败风险比较。
- 不把故障注入比例解释为自然运营故障率。
- 不把最小雷达观测值解释为物理净距或安全认证。
