-- 业务问题：roa-data-v0.1 是否满足进入 W6 正式分析的三层数据契约？
-- 输入粒度：fact_task_execution 每任务一行；fact_task_event 每事件一行；
--           fact_task_telemetry_1s 每任务每仿真秒一行。
-- 过滤条件：任务限定 dataset_version='roa-data-v0.1'、run_origin='natural'、
--           data_quality_valid=TRUE；事件和遥测通过 task_id 归入该任务队列。
-- 输出粒度：单行门禁结果；quality_gate_passed=TRUE 才允许执行后续正式分析。
-- 限制：81/7391/1368 是冻结数据版本的精确行数，不代表真实运营规模；
--       本查询只验证结构、一致性和覆盖关系，不证明业务结论正确或具有因果性。

WITH
cohort AS (
    SELECT *
    FROM fact_task_execution
    WHERE dataset_version = 'roa-data-v0.1'
      AND run_origin = 'natural'
      AND data_quality_valid = TRUE
),
task_checks AS (
    SELECT
        COUNT(*) AS task_count,
        COUNT(*) - COUNT(DISTINCT task_id) AS duplicate_task_keys,
        COUNT(*) FILTER (
            WHERE task_id IS NULL OR source_batch_id IS NULL OR experiment_id IS NULL
               OR request_id IS NULL OR route_id IS NULL OR obstacle_profile IS NULL
               OR localization_perturbation_level IS NULL OR parameter_version IS NULL
               OR terminal_status IS NULL OR cycle_time_sec IS NULL
        ) AS task_required_null_rows,
        COUNT(*) FILTER (
            WHERE terminal_status NOT IN ('success', 'failed', 'canceled', 'timeout')
               OR (terminal_status = 'success') <> (success = TRUE)
               OR terminal_at_sim < accepted_at_sim OR cycle_time_sec < 0
               OR valid_telemetry_bucket_count > telemetry_bucket_count
        ) AS task_semantic_error_rows,
        COALESCE(SUM(telemetry_bucket_count), 0) AS declared_telemetry_bucket_count
    FROM cohort
),
event_checks AS (
    SELECT
        COUNT(*) AS event_count,
        COUNT(*) - COUNT(DISTINCT (task_id, event_sequence)) AS duplicate_event_keys,
        COUNT(*) FILTER (
            WHERE task_id IS NULL OR event_sequence IS NULL
               OR event_time_sim IS NULL OR event_type IS NULL
        ) AS event_required_null_rows,
        COUNT(DISTINCT task_id) AS event_task_coverage
    FROM fact_task_event
),
telemetry_checks AS (
    SELECT
        COUNT(*) AS telemetry_bucket_count,
        COUNT(*) - COUNT(DISTINCT (task_id, bucket_start_sim)) AS duplicate_telemetry_keys,
        COUNT(*) FILTER (
            WHERE task_id IS NULL OR bucket_start_sim IS NULL OR bucket_end_sim IS NULL
               OR required_topics_present IS NULL OR timestamp_valid IS NULL
               OR stale_sensor_mask IS NULL
        ) AS telemetry_required_null_rows,
        COUNT(*) FILTER (WHERE bucket_end_sim <= bucket_start_sim) AS telemetry_time_error_rows,
        COUNT(DISTINCT task_id) AS telemetry_task_coverage
    FROM fact_task_telemetry_1s
),
relationship_checks AS (
    SELECT
        (SELECT COUNT(*) FROM fact_task_event e
         LEFT JOIN cohort t USING (task_id) WHERE t.task_id IS NULL) AS orphan_event_rows,
        (SELECT COUNT(*) FROM fact_task_telemetry_1s m
         LEFT JOIN cohort t USING (task_id) WHERE t.task_id IS NULL) AS orphan_telemetry_rows
)
SELECT
    t.task_count,
    e.event_count,
    m.telemetry_bucket_count,
    e.event_task_coverage,
    m.telemetry_task_coverage,
    t.declared_telemetry_bucket_count,
    t.duplicate_task_keys,
    e.duplicate_event_keys,
    m.duplicate_telemetry_keys,
    t.task_required_null_rows,
    e.event_required_null_rows,
    m.telemetry_required_null_rows,
    t.task_semantic_error_rows,
    m.telemetry_time_error_rows,
    r.orphan_event_rows,
    r.orphan_telemetry_rows,
    (
        t.task_count = 81
        AND e.event_count = 7391
        AND m.telemetry_bucket_count = 1368
        AND e.event_task_coverage = t.task_count
        AND m.telemetry_task_coverage = t.task_count
        AND t.declared_telemetry_bucket_count = m.telemetry_bucket_count
        AND t.duplicate_task_keys = 0
        AND e.duplicate_event_keys = 0
        AND m.duplicate_telemetry_keys = 0
        AND t.task_required_null_rows = 0
        AND e.event_required_null_rows = 0
        AND m.telemetry_required_null_rows = 0
        AND t.task_semantic_error_rows = 0
        AND m.telemetry_time_error_rows = 0
        AND r.orphan_event_rows = 0
        AND r.orphan_telemetry_rows = 0
    ) AS quality_gate_passed
FROM task_checks t
CROSS JOIN event_checks e
CROSS JOIN telemetry_checks m
CROSS JOIN relationship_checks r;
