-- 业务问题：任务周期的典型水平和长尾分别集中在哪些终态与路线？
-- 输入粒度：fact_task_execution 每任务一行。
-- 过滤条件：dataset_version='roa-data-v0.1'、run_origin='natural'、
--           data_quality_valid=TRUE且cycle_time_sec非空。
-- 输出粒度：整体一行、每个终态一行、每条路线一行；不同维度之间不得相加。
-- 限制：分位数为探索性描述，小样本组标记为small_sample；路线差异仅表示相关性，
--       控制变量实验完成前不得解释为路线导致周期变化。

WITH cohort AS (
    SELECT
        task_id,
        terminal_status,
        route_id,
        cycle_time_sec
    FROM fact_task_execution
    WHERE dataset_version = 'roa-data-v0.1'
      AND run_origin = 'natural'
      AND data_quality_valid = TRUE
      AND cycle_time_sec IS NOT NULL
),
grouped AS (
    SELECT 'overall' AS dimension_type, 'overall' AS dimension_value,
           task_id, terminal_status, cycle_time_sec
    FROM cohort
    UNION ALL
    SELECT 'terminal_status', terminal_status, task_id, terminal_status, cycle_time_sec
    FROM cohort
    UNION ALL
    SELECT 'route_id', route_id, task_id, terminal_status, cycle_time_sec
    FROM cohort
),
distribution AS (
    SELECT
        dimension_type,
        dimension_value,
        COUNT(*) AS task_count,
        COUNT(*) FILTER (WHERE terminal_status = 'success') AS success_count,
        COUNT(*) FILTER (WHERE terminal_status <> 'success') AS failure_count,
        AVG(cycle_time_sec) AS mean_cycle_time_sec,
        quantile_cont(cycle_time_sec, 0.50) AS p50_cycle_time_sec,
        quantile_cont(cycle_time_sec, 0.90) AS p90_cycle_time_sec,
        quantile_cont(cycle_time_sec, 0.95) AS p95_cycle_time_sec,
        MIN(cycle_time_sec) AS min_cycle_time_sec,
        MAX(cycle_time_sec) AS max_cycle_time_sec
    FROM grouped
    GROUP BY dimension_type, dimension_value
)
SELECT
    dimension_type,
    dimension_value,
    task_count,
    success_count,
    failure_count,
    mean_cycle_time_sec,
    p50_cycle_time_sec,
    p90_cycle_time_sec,
    p95_cycle_time_sec,
    min_cycle_time_sec,
    max_cycle_time_sec,
    CASE WHEN task_count < 10 THEN 'small_sample' ELSE 'adequate_for_exploration' END
        AS sample_size_flag
FROM distribution
ORDER BY
    CASE dimension_type WHEN 'overall' THEN 0 WHEN 'terminal_status' THEN 1 ELSE 2 END,
    dimension_value;
