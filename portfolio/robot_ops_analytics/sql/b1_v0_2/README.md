# B1 v0.2 SQL目录

- `00_data_contract_checks.sql`：冻结队列、三层行数、分组平衡和污染门禁；
- `01_obstacle_kpis.sql`：完成率、失败率及周期P50/P90/P95；
- `02_task_telemetry_features.sql`：每任务横向偏移与护栏特征；
- `03_obstacle_guardrails.sql`：按障碍档位汇总绕行和观测护栏。
- `04_cross_version_comparison.sql`：同时查询旧版与B1，分别计算后并列对照。

执行和对账入口为`pipelines/b1_v0_2/reconcile_w6_sql.py`。旧版与B1只分别计算并列展示，禁止
合并为一个总体估计。
