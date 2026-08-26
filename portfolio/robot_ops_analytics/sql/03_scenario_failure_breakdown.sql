-- 业务问题：失败分别集中在哪些路线、障碍、定位扰动及三者组合？
-- 输入粒度：fact_task_execution 每任务一行。
-- 过滤条件：dataset_version='roa-data-v0.1'、run_origin='natural'、
--           data_quality_valid=TRUE。
-- 输出粒度：路线、障碍、定位扰动各一维分组，以及路线×障碍×扰动组合分组；
--           不同dimension_type之间不得相加。
-- 限制：failure_rate描述组内风险，failure_contribution描述该组占全部失败的比例；
--       组合组少于5项时标记small_sample。结果只表示相关性，不证明场景因素导致失败。

WITH cohort AS (
    SELECT
        task_id,
        route_id,
        obstacle_profile,
        localization_perturbation_level,
        terminal_status,
        cycle_time_sec
    FROM fact_task_execution
    WHERE dataset_version = 'roa-data-v0.1'
      AND run_origin = 'natural'
      AND data_quality_valid = TRUE
),
total AS (
    SELECT COUNT(*) FILTER (WHERE terminal_status <> 'success') AS total_failure_count
    FROM cohort
),
grouped AS (
    SELECT 'route_id' AS dimension_type,
           route_id AS route_id,
           NULL::VARCHAR AS obstacle_profile,
           NULL::VARCHAR AS localization_perturbation_level,
           task_id, terminal_status, cycle_time_sec
    FROM cohort
    UNION ALL
    SELECT 'obstacle_profile', NULL, obstacle_profile, NULL,
           task_id, terminal_status, cycle_time_sec
    FROM cohort
    UNION ALL
    SELECT 'localization_perturbation_level', NULL, NULL,
           localization_perturbation_level,
           task_id, terminal_status, cycle_time_sec
    FROM cohort
    UNION ALL
    SELECT 'scenario_combination', route_id, obstacle_profile,
           localization_perturbation_level,
           task_id, terminal_status, cycle_time_sec
    FROM cohort
),
breakdown AS (
    SELECT
        dimension_type,
        route_id,
        obstacle_profile,
        localization_perturbation_level,
        COUNT(*) AS task_count,
        COUNT(*) FILTER (WHERE terminal_status = 'success') AS success_count,
        COUNT(*) FILTER (WHERE terminal_status <> 'success') AS failure_count,
        COUNT(*) FILTER (WHERE terminal_status <> 'success')::DOUBLE
            / NULLIF(COUNT(*), 0) AS failure_rate,
        AVG(cycle_time_sec) AS mean_cycle_time_sec,
        quantile_cont(cycle_time_sec, 0.50) AS p50_cycle_time_sec,
        quantile_cont(cycle_time_sec, 0.95) AS p95_cycle_time_sec
    FROM grouped
    GROUP BY dimension_type, route_id, obstacle_profile,
             localization_perturbation_level
)
SELECT
    b.dimension_type,
    b.route_id,
    b.obstacle_profile,
    b.localization_perturbation_level,
    b.task_count,
    b.success_count,
    b.failure_count,
    b.failure_rate,
    b.failure_count::DOUBLE / NULLIF(t.total_failure_count, 0) AS failure_contribution,
    b.mean_cycle_time_sec,
    b.p50_cycle_time_sec,
    b.p95_cycle_time_sec,
    CASE WHEN b.task_count < 5 THEN 'small_sample' ELSE 'adequate_for_exploration' END
        AS sample_size_flag
FROM breakdown b
CROSS JOIN total t
ORDER BY
    CASE b.dimension_type
        WHEN 'route_id' THEN 0
        WHEN 'obstacle_profile' THEN 1
        WHEN 'localization_perturbation_level' THEN 2
        ELSE 3
    END,
    failure_contribution DESC,
    b.failure_rate DESC,
    b.route_id,
    b.obstacle_profile,
    b.localization_perturbation_level;
