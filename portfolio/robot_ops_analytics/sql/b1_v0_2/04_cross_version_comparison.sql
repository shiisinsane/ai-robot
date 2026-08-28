-- 业务问题：旧版探索基线与B1控制实验在共同任务指标下分别呈现什么结果？
-- 前置条件：当前连接为B1数据库，并将旧版数据库ATTACH为legacy。
-- 计算规则：两个版本分别过滤、分别聚合，只用UNION ALL并列输出，禁止混表总体估计。
-- 输出粒度：每个数据版本一行。
-- 限制：两版路线、场景构成、定位扰动和实验目的不同，版本间差异不是升级效果或因果效应。

WITH legacy_cohort AS (
    SELECT terminal_status, cycle_time_sec
    FROM legacy.fact_task_execution
    WHERE dataset_version = 'roa-data-v0.1'
      AND run_origin = 'natural'
      AND data_quality_valid = TRUE
), b1_cohort AS (
    SELECT terminal_status, cycle_time_sec
    FROM fact_task_execution
    WHERE dataset_version = 'roa-validation-b1-v0.2'
      AND run_origin = 'natural'
      AND data_quality_valid = TRUE
), comparison AS (
    SELECT
        'roa-data-v0.1' AS dataset_version,
        '多路线探索基线' AS design_role,
        COUNT(*) AS task_count,
        COUNT(*) FILTER (WHERE terminal_status = 'success') AS success_count,
        COUNT(*) FILTER (WHERE terminal_status <> 'success') AS failure_count,
        COUNT(*) FILTER (WHERE terminal_status = 'success')::DOUBLE / COUNT(*) AS completion_rate,
        COUNT(*) FILTER (WHERE terminal_status <> 'success')::DOUBLE / COUNT(*) AS failure_rate,
        AVG(cycle_time_sec) AS mean_cycle_time_sec,
        quantile_cont(cycle_time_sec, 0.50) AS p50_cycle_time_sec,
        quantile_cont(cycle_time_sec, 0.90) AS p90_cycle_time_sec,
        quantile_cont(cycle_time_sec, 0.95) AS p95_cycle_time_sec
    FROM legacy_cohort

    UNION ALL

    SELECT
        'roa-validation-b1-v0.2',
        '固定4米路线控制实验',
        COUNT(*),
        COUNT(*) FILTER (WHERE terminal_status = 'success'),
        COUNT(*) FILTER (WHERE terminal_status <> 'success'),
        COUNT(*) FILTER (WHERE terminal_status = 'success')::DOUBLE / COUNT(*),
        COUNT(*) FILTER (WHERE terminal_status <> 'success')::DOUBLE / COUNT(*),
        AVG(cycle_time_sec),
        quantile_cont(cycle_time_sec, 0.50),
        quantile_cont(cycle_time_sec, 0.90),
        quantile_cont(cycle_time_sec, 0.95)
    FROM b1_cohort
)
SELECT * FROM comparison
ORDER BY CASE dataset_version WHEN 'roa-data-v0.1' THEN 0 ELSE 1 END;
