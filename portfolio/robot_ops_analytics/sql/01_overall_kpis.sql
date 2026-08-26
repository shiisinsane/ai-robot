-- 业务问题：冻结队列的整体完成能力和按终态划分的周转效率如何？
-- 输入粒度：fact_task_execution 每任务一行。
-- 过滤条件：dataset_version='roa-data-v0.1'、run_origin='natural'、
--           data_quality_valid=TRUE。
-- 输出粒度：一行 overall，加上每个实际出现的 terminal_status 一行。
-- 限制：当前没有冻结的机器人 Ready 运行窗口，因此不计算单位机器人小时有效任务数；
--       完成率和失败率仅描述 81 项受控仿真探索基线，不外推自然运营故障率。

WITH cohort AS (
    SELECT
        task_id,
        terminal_status,
        cycle_time_sec
    FROM fact_task_execution
    WHERE dataset_version = 'roa-data-v0.1'
      AND run_origin = 'natural'
      AND data_quality_valid = TRUE
),
kpis AS (
    SELECT
        CASE WHEN GROUPING(terminal_status) = 1 THEN 'overall' ELSE terminal_status END
            AS result_scope,
        COUNT(*) AS task_count,
        COUNT(*) FILTER (WHERE terminal_status = 'success') AS success_count,
        COUNT(*) FILTER (WHERE terminal_status <> 'success') AS failure_count,
        COUNT(*) FILTER (WHERE terminal_status = 'success')::DOUBLE / NULLIF(COUNT(*), 0)
            AS completion_rate,
        COUNT(*) FILTER (WHERE terminal_status <> 'success')::DOUBLE / NULLIF(COUNT(*), 0)
            AS failure_rate,
        AVG(cycle_time_sec) AS mean_cycle_time_sec,
        quantile_cont(cycle_time_sec, 0.50) AS p50_cycle_time_sec,
        quantile_cont(cycle_time_sec, 0.90) AS p90_cycle_time_sec,
        quantile_cont(cycle_time_sec, 0.95) AS p95_cycle_time_sec
    FROM cohort
    GROUP BY GROUPING SETS ((), (terminal_status))
)
SELECT
    result_scope,
    task_count,
    success_count,
    failure_count,
    completion_rate,
    failure_rate,
    mean_cycle_time_sec,
    p50_cycle_time_sec,
    p90_cycle_time_sec,
    p95_cycle_time_sec
FROM kpis
ORDER BY CASE WHEN result_scope = 'overall' THEN 0 ELSE 1 END, result_scope;
