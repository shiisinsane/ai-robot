# W5 SQLite原始接入报告

> 数据版本：`roa-data-v0.1`
> 状态：白名单接入、顺序重复回放及SQLite WAL并发/中断恢复验收通过
> 限制：本报告只验收原始接入层，不代表MySQL并发能力；事实层结果见后续W5报告

## 输入与白名单

接入程序只读取W5审计清单中81个任务对应的W4运行索引和结构化记录。清单外任务不会写入
SQLite；审计清单自身未通过质量门禁时，接入程序直接退出。

## 首次接入

- 源批次：73；
- 唯一任务：81；
- 扫描并插入原始记录：24446；
- 重复拦截：0；
- 文件水位：146。

记录类型对账：

| 类型 | 行数 |
|---|---:|
| `run_result` | 81 |
| `task_context` | 7391 |
| `task_telemetry_1s` | 1368 |
| `diagnostics` | 15606 |
| 合计 | 24446 |

## 重复回放

对同一81项数据执行第二次完整回放：扫描24446条、插入0条、唯一约束拦截24446条；数据库
仍为24446条原始记录和81个唯一任务。该结果证明相同源文件的重复接入具备幂等性，但不等于
已经验证MySQL并发、SQLite多进程竞争、死锁重试或性能容量。

## 产物

- SQLite：`artifacts/roa_w5/roa-data-v0.1/raw_ingestion.sqlite`，21311488字节；
- SQLite SHA-256：`e7af428b1b18d3665e0e2dbf1dd89ea56b099f390bdc28e22907ae0fa42443bd`；
- 首次接入报告SHA-256：`50c3961e801fbf9fde152df37240c243e297d28371616b93157cbf5cb74d58a2`；
- 重复回放报告SHA-256：`b9f66574c988c0cfa392502759c17c6b2bcfd5237ea9fadc1c3d318411a0c63f`。

## SQLite WAL并发与恢复验证

2026-08-25使用4个独立进程对完整`roa-data-v0.1`执行分片回放。验证覆盖相反批次顺序、随机
到达延迟、3次跨进程重叠批次，以及首批事务写入中途故障。中断事务完整回滚，恢复后结果为：

- 73个源批次、81个唯一任务、24446条原始记录；
- 146个文件checkpoint、0个质量问题；
- SQLite运行于WAL模式，`PRAGMA integrity_check`结果为`ok`；
- 重叠批次由唯一约束拦截，未产生重复事实；
- 验证报告：`artifacts/roa_w5/roa-data-v0.1/concurrent_replay_20260825.json`。

该验证证明当前SQLite原始接入层可处理本数据集规模的多进程竞争、批次乱序、随机延迟和批次
事务中断恢复；不外推为MySQL事务隔离、死锁重试、连接池或生产容量验证。

## 后续门禁状态

任务、事件和遥测事实表增量ETL及SQLite质量对账已于2026-08-25完成，结果见
`reports/legacy_v0_1/w5_fact_etl_v0.1.md`和`reports/legacy_v0_1/w5_data_quality_v0.1.md`。DuckDB/Parquet及MySQL集成仍未完成。
