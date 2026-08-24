# W5 ETL与数据质量运行手册

> 状态：已完成基线质量门禁及SQLite原始层幂等接入；并发回放与事实表加工待实现。

## 1. 当前输入

- 数据版本：`roa-data-v0.1`；
- 来源：W4 baseline自然运行81项；
- 用途：ETL开发、数据画像和补采方案设计；
- 限制：不是冻结模型测试集，不用于估计真实生产故障率。

## 2. 基线审计

```bash
python3 -m portfolio.robot_ops_analytics.etl.audit_baseline \
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
python3 -m portfolio.robot_ops_analytics.etl.ingest_sqlite \
  --database artifacts/roa_w5/roa-data-v0.1/raw_ingestion.sqlite \
  --manifest artifacts/roa_w5/roa-data-v0.1/baseline_audit.json \
  --report artifacts/roa_w5/roa-data-v0.1/ingestion_first.json
```

原始层使用W5审计清单作为任务白名单，通过`dataset_version + source_batch_id + source_file +
source_line_number + payload_sha256`生成幂等键。每个源文件维护扫描水位；重复执行不会增加
`raw_record`行数。详细结果见`reports/w5_raw_ingestion_v0.1.md`。

## 5. 下一实现

先执行SQLite WAL多进程回放，验证重复、乱序、延迟和中断恢复；再将原始层加工为仓库事实表。
当前环境尚未安装DuckDB和PyArrow，因此本轮不声称已生成DuckDB/Parquet；依赖准备后再实现
对应落盘层及确定性测试。
