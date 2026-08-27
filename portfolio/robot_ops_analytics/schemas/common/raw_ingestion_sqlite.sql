-- W5 SQLite原始接入层v1.0；用于本地幂等与增量ETL开发。

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS ingestion_batch (
    ingestion_batch_id TEXT PRIMARY KEY,
    dataset_version TEXT NOT NULL,
    source_batch_id TEXT NOT NULL,
    source_uri TEXT NOT NULL,
    first_ingested_at TEXT NOT NULL,
    last_replayed_at TEXT NOT NULL,
    replay_count INTEGER NOT NULL DEFAULT 1 CHECK (replay_count >= 1),
    UNIQUE (dataset_version, source_batch_id)
);

CREATE TABLE IF NOT EXISTS raw_record (
    raw_record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    ingestion_batch_id TEXT NOT NULL REFERENCES ingestion_batch(ingestion_batch_id),
    dataset_version TEXT NOT NULL,
    source_batch_id TEXT NOT NULL,
    source_file TEXT NOT NULL CHECK (source_file IN ('run_results.jsonl', 'records.jsonl')),
    source_line_number INTEGER NOT NULL CHECK (source_line_number >= 1),
    record_type TEXT NOT NULL,
    task_id TEXT NOT NULL,
    event_time_sim DOUBLE,
    payload_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    received_at TEXT NOT NULL,
    UNIQUE (dataset_version, source_batch_id, source_file, source_line_number)
);

CREATE TABLE IF NOT EXISTS etl_checkpoint (
    dataset_version TEXT NOT NULL,
    source_batch_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    last_scanned_line INTEGER NOT NULL CHECK (last_scanned_line >= 0),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (dataset_version, source_batch_id, source_file)
);

CREATE TABLE IF NOT EXISTS data_quality_issue (
    issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_version TEXT NOT NULL,
    source_batch_id TEXT,
    task_id TEXT,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'error')),
    details TEXT NOT NULL,
    detected_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_record_task ON raw_record(task_id);
CREATE INDEX IF NOT EXISTS idx_raw_record_type ON raw_record(record_type);
CREATE INDEX IF NOT EXISTS idx_raw_record_batch ON raw_record(source_batch_id);
