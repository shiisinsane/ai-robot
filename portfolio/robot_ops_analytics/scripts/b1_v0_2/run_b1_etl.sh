#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
DATASET_VERSION="roa-validation-b1-v0.2"
SOURCE_ROOT="${REPO_ROOT}/artifacts/roa_b1/${DATASET_VERSION}"
OUTPUT_ROOT="${SOURCE_ROOT}/etl"

if [[ "${1:-}" == "--check" ]]; then
  test -f "${OUTPUT_ROOT}/whitelist_manifest.json"
  test -f "${OUTPUT_ROOT}/raw_ingestion.sqlite"
  test -f "${OUTPUT_ROOT}/analysis.sqlite"
  test -f "${OUTPUT_ROOT}/analytics.duckdb"
  echo "B1 ETL产物齐全：${OUTPUT_ROOT}"
  exit 0
fi

if [[ -e "${OUTPUT_ROOT}/raw_ingestion.sqlite" || -e "${OUTPUT_ROOT}/analysis.sqlite" ]]; then
  echo "拒绝覆盖已存在的B1数据库：${OUTPUT_ROOT}" >&2
  echo "当前数据已封板；如需重建，请使用新的输出目录和数据版本。" >&2
  exit 2
fi

cd "${REPO_ROOT}"
python3 -m portfolio.robot_ops_analytics.pipelines.b1_v0_2.build_b1_manifest \
  --dataset-root "${SOURCE_ROOT}" \
  --output "${OUTPUT_ROOT}/whitelist_manifest.json"
python3 -m portfolio.robot_ops_analytics.pipelines.common.ingest_sqlite \
  --database "${OUTPUT_ROOT}/raw_ingestion.sqlite" \
  --manifest "${OUTPUT_ROOT}/whitelist_manifest.json" \
  --report "${OUTPUT_ROOT}/raw_ingestion_report.json"
cp "${OUTPUT_ROOT}/raw_ingestion.sqlite" "${OUTPUT_ROOT}/analysis.sqlite"
python3 -m portfolio.robot_ops_analytics.pipelines.common.build_facts_sqlite \
  --database "${OUTPUT_ROOT}/analysis.sqlite" \
  --report "${OUTPUT_ROOT}/fact_build_report.json"
python3 -m portfolio.robot_ops_analytics.pipelines.common.audit_facts_sqlite \
  --database "${OUTPUT_ROOT}/analysis.sqlite" \
  --report "${OUTPUT_ROOT}/fact_quality_report.json"
conda run -n roa-w5 python -m portfolio.robot_ops_analytics.pipelines.common.export_parquet_duckdb \
  --sqlite-database "${OUTPUT_ROOT}/analysis.sqlite" \
  --parquet-dir "${OUTPUT_ROOT}/parquet" \
  --duckdb-database "${OUTPUT_ROOT}/analytics.duckdb" \
  --dataset-version "${DATASET_VERSION}" \
  --export-version "roa-parquet-b1-v0.2" \
  --report "${OUTPUT_ROOT}/export_quality_report.json"
