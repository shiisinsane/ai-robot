# W5 ETL与数据质量运行手册

> 状态：2026-08-25正式验收通过；下一入口为W6核心SQL业务分析。

## 1. 当前输入

- 数据版本：`roa-data-v0.1`；
- 来源：W4 baseline自然运行81项；
- 用途：ETL开发、数据画像和补采方案设计；
- 限制：不是冻结模型测试集，不用于估计真实生产故障率。

## 2. 基线审计

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.common.audit_baseline \
  --dataset-root artifacts/roa_w4/roa-data-v0.1 \
  --dataset-version roa-data-v0.1 \
  --output artifacts/roa_w5/roa-data-v0.1/baseline_audit.json
```

审计按任务而非批次计数，允许一个历史Pilot批次包含多个任务。每项任务必须满足：运行索引唯一、
终态唯一、Runner返回码与Action终态一致、整秒遥测Topic和时间戳完整、rosbag非空，以及本批
进程残留检查通过。跨批次任务ID重复会使整个质量门禁失败。

## 3. 迭代补采规则

1. 先使用`roa-data-v0.1`完成ETL和探索分析；
2. 补采前记录目标场景、样本数、停止条件和用途；
3. 自然运行与故障注入分别标记和报告，不用注入分布估计自然故障率；
4. 所有有效成功和失败均保留，不按模型表现挑选样本；
5. 建模前冻结批次级训练、验证和测试清单；测试集冻结后不用于补采或调参决策。

## 4. SQLite原始接入

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.common.ingest_sqlite \
  --database artifacts/roa_w5/roa-data-v0.1/raw_ingestion.sqlite \
  --manifest artifacts/roa_w5/roa-data-v0.1/baseline_audit.json \
  --report artifacts/roa_w5/roa-data-v0.1/ingestion_first.json
```

原始层使用W5审计清单作为任务白名单，通过`dataset_version + source_batch_id + source_file +
source_line_number + payload_sha256`生成幂等键。每个源文件维护扫描水位；重复执行不会增加
`raw_record`行数。详细结果见`reports/legacy_v0_1/w5_raw_ingestion_v0.1.md`。

## 5. 并发、乱序与中断恢复验证

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.legacy_v0_1.validate_concurrent_replay \
  --database /tmp/roa_w5_concurrent.sqlite \
  --manifest artifacts/roa_w5/roa-data-v0.1/baseline_audit.json \
  --workers 4 \
  --report artifacts/roa_w5/roa-data-v0.1/concurrent_replay.json
```

验证数据库必须是不存在的新路径。工具先在首批事务中注入中断并确认完整回滚，再由多个独立
进程分片回放全部批次；相邻进程使用相反批次顺序，并额外制造跨进程重复和随机到达延迟。
验收要求为SQLite完整性通过、WAL模式生效、81项任务和24446条记录不丢失、146个文件
checkpoint齐全且质量问题为0。

2026-08-25已使用4个进程对`roa-data-v0.1`完成验证，详细结果见
`artifacts/roa_w5/roa-data-v0.1/concurrent_replay_20260825.json`。

## 6. 增量事实表加工

为避免改变已冻结的原始接入数据库，先复制到分析工作库，再运行：

```bash
cp artifacts/roa_w5/roa-data-v0.1/raw_ingestion.sqlite \
  artifacts/roa_w5/roa-data-v0.1/analysis.sqlite
python3 -m portfolio.robot_ops_analytics.pipelines.common.build_facts_sqlite \
  --database artifacts/roa_w5/roa-data-v0.1/analysis.sqlite \
  --report artifacts/roa_w5/roa-data-v0.1/fact_build.json
```

事实层使用`raw_record_id`高水位作为checkpoint。每次只识别水位后的受影响任务，但会使用该任务
全部原始记录重建事实，因而能够吸收迟到事件；事实写入和checkpoint更新位于同一事务。当前生成
`fact_task_execution`、`fact_task_event`和`fact_task_telemetry_1s`，只保存原始载荷能够证明的字段，
不使用猜测值填充缺失维度。

2026-08-25首轮完整加工得到81行任务事实、7391行事件事实和1368行整秒遥测事实；第二次无新增
运行识别0项受影响任务。详细结果见`reports/legacy_v0_1/w5_fact_etl_v0.1.md`。

## 7. 数据质量与对账

```bash
python3 -m portfolio.robot_ops_analytics.pipelines.common.audit_facts_sqlite \
  --database artifacts/roa_w5/roa-data-v0.1/analysis.sqlite \
  --report artifacts/roa_w5/roa-data-v0.1/fact_quality_v0.1.json
```

最终验收结果为21条规则全部通过、违规0项。81项任务、7391条事件和1368个遥测桶在原始层与事实层
差异均为0；任务同时连接事件和遥测会形成225511个物理行，去重后仍为81项任务，因此任务级
指标禁止直接对跨事实Join执行`COUNT(*)`。详见`reports/legacy_v0_1/w5_data_quality_v0.1.md`。

## 8. Parquet与DuckDB分析层

```bash
source /home/yangyiyao/miniconda3/etc/profile.d/conda.sh
conda env create -f portfolio/robot_ops_analytics/environment-analytics.yml
conda activate roa-w5
python -m portfolio.robot_ops_analytics.pipelines.common.export_parquet_duckdb \
  --sqlite-database artifacts/roa_w5/roa-data-v0.1/analysis.sqlite \
  --parquet-dir artifacts/roa_w5/roa-data-v0.1/parquet \
  --duckdb-database artifacts/roa_w5/roa-data-v0.1/analytics.duckdb \
  --report artifacts/roa_w5/roa-data-v0.1/parquet_duckdb_v0.1.json
```

三张事实表在SQLite、Parquet与DuckDB中的行数完全一致，重复主键和必填字段空值均为0；DuckDB
视图可直接查询出成功66项、失败15项。版本、哈希和详细对账见
`reports/legacy_v0_1/w5_parquet_duckdb_v0.1.md`。

## 9. 验收结论

W5正式基线执行21条质量规则且违规0项，脏数据夹具与完整数据复验通过，详见
`reports/acceptance/w5_acceptance_20260825.md`。本手册后续只用于复现W5；新增分析工作从W6文档进入。
