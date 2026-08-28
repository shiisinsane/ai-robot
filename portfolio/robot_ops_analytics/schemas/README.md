# Schema与ETL版本索引

本目录把通用定义、版本契约和证据清单分开管理。不要根据文件修改时间猜测新旧版本。

```text
schemas/
├── common/       # 通用DDL、数据字典、指标字典和维度种子
├── versions/     # 每个数据版本采用的Schema路径与SHA-256
└── evidence/     # 证据模板和已生成的证据清单
```

| 数据版本 | 状态 | Schema契约 | 流水线契约 | 数据位置 |
|---|---|---|---|---|
| `roa-data-v0.1` | `retired`，仅追溯 | `versions/roa-data-v0.1/contract.yaml` | `pipelines/roa-data-v0.1.yaml` | `artifacts/roa_w5/roa-data-v0.1/` |
| `roa-validation-b1-v0.2` | `current`，当前正式分析 | `versions/roa-validation-b1-v0.2/contract.yaml` | `pipelines/roa-validation-b1-v0.2.yaml` | `artifacts/roa_b1/roa-validation-b1-v0.2/etl/` |
| `roa-b2-qualification-v0.1` | `current_preexecution_contract` | `versions/roa-b2-qualification-v0.1/contract.yaml` | B2冻结计划与运行时参数门禁 | `artifacts/roa_b2/`诊断批次 |

## 文件分工

- `common/raw_ingestion_sqlite.sql`：原始接入层表结构；
- `common/analytics_facts_sqlite.sql`：任务、事件和整秒遥测事实层表结构；
- `common/warehouse.sql`、`common/data_dictionary.yaml`：W2完整仓库设计；
- `common/metric_dictionary.yaml`：指标口径，不负责建表；
- `versions/*/contract.yaml`：锁定某个数据版本采用的Schema及SHA-256；
- `evidence/`：实验凭证模板及实例，不参与SQLite建表；
- `../pipelines/*.yaml`：锁定输入、步骤、脚本和输出位置。

当前B1数据只允许通过`roa-validation-b1-v0.2`契约分析。旧版可用于问题发现和追溯，但不得与
B1合并计算正式指标。
