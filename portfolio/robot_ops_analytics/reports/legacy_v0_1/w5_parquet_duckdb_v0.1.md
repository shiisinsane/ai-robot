# W5 Parquet与DuckDB分析层报告

> 数据版本：`roa-data-v0.1`
> 导出版本：`roa-parquet-v0.1`
> 日期：2026-08-25
> 结论：SQLite、Parquet与DuckDB三层对账通过

## 环境与复现

- Python：3.10；
- DuckDB：1.4.3；
- PyArrow：24.0.0；
- Conda环境定义：`environment-analytics.yml`；
- 导出入口：`pipelines/common/export_parquet_duckdb.py`。

## 正式产物

| 产物 | 行数 | 大小（字节） | SHA-256 |
|---|---:|---:|---|
| `fact_task_execution.parquet` | 81 | 21209 | `49f825fbc383d28a05b143e8b25b5c4fcde1a2cb0b2422def82f57c3ef5c4d09` |
| `fact_task_event.parquet` | 7391 | 72109 | `795e80436cb5b372f7bc7e947b6e2de6c416106a4268c97b295ce08ad9af03df` |
| `fact_task_telemetry_1s.parquet` | 1368 | 145507 | `f7c85b7bdf56e87bc304153daca843c476d138e00a33852977dc24e150ddc78e` |
| `analytics.duckdb` | 3个视图 | 798720 | `382ad7f14ea877ba4e5a5abbf86ef90066dfc89f7ed17c5cde023e2bd376d415` |

大型数据产物保存在`artifacts/roa_w5/roa-data-v0.1/`并由Git忽略，仓库只保存生成代码、环境定义、
测试和本报告。

## 三层对账

| 表 | SQLite | Parquet | DuckDB | 重复主键 | 必填字段空值 |
|---|---:|---:|---:|---:|---:|
| 任务事实 | 81 | 81 | 81 | 0 | 0 |
| 事件事实 | 7391 | 7391 | 7391 | 0 | 0 |
| 整秒遥测事实 | 1368 | 1368 | 1368 | 0 | 0 |

DuckDB跨事实Join后`COUNT(DISTINCT task_id)`仍为81。实际查询得到成功66项、失败15项，证明三个
Parquet视图可以直接用于后续W6 SQL分析。

## 边界

DuckDB视图引用外部Parquet文件，移动数据目录后应重新运行导出工具刷新路径。本结果验证本地
分析交付层，不代表MySQL并发、分布式数据仓库或生产容量。
