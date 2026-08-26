-- 业务问题：失败是否按墙上启动顺序连续出现，或集中在特定场景与采集时段？
-- 输入粒度：fact_task_execution每任务一行。
-- 过滤条件：正式自然运行有效任务；以started_at_wall、task_id建立确定性全局顺序。
-- 输出粒度：每个连续失败段一行；相邻失败之间没有成功任务才属于同一段。
-- 限制：采集顺序并非随机化顺序，场景本身按实验计划成组运行；连续失败可能反映场景聚集，
--       不能单凭时间相邻推断环境状态漂移或前一任务导致后一任务失败。

WITH cohort AS (
    SELECT
        task_id,
        source_batch_id,
        CAST(started_at_wall AS TIMESTAMP) AS started_at_wall,
        terminal_status,
        route_id,
        obstacle_profile,
        localization_perturbation_level,
        terminal_status <> 'success' AS is_failure
    FROM fact_task_execution
    WHERE dataset_version = 'roa-data-v0.1'
      AND run_origin = 'natural'
      AND data_quality_valid = TRUE
),
ordered AS (
    SELECT
        *,
        ROW_NUMBER() OVER (ORDER BY started_at_wall, task_id) AS run_order,
        LAG(task_id) OVER (ORDER BY started_at_wall, task_id) AS previous_task_id,
        LAG(started_at_wall) OVER (ORDER BY started_at_wall, task_id)
            AS previous_started_at_wall,
        LAG(terminal_status) OVER (ORDER BY started_at_wall, task_id)
            AS previous_terminal_status,
        LAG(is_failure, 1, FALSE) OVER (ORDER BY started_at_wall, task_id)
            AS previous_is_failure
    FROM cohort
),
marked AS (
    SELECT
        *,
        is_failure AND NOT previous_is_failure AS starts_failure_streak
    FROM ordered
),
numbered AS (
    SELECT
        *,
        SUM(CASE WHEN starts_failure_streak THEN 1 ELSE 0 END) OVER (
            ORDER BY run_order ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS failure_streak_id
    FROM marked
),
failure_rows AS (
    SELECT * FROM numbered WHERE is_failure
)
SELECT
    failure_streak_id,
    MIN(run_order) AS start_run_order,
    MAX(run_order) AS end_run_order,
    COUNT(*) AS consecutive_failure_count,
    MIN(started_at_wall) AS streak_started_at_wall,
    MAX(started_at_wall) AS streak_ended_at_wall,
    MIN(previous_task_id) FILTER (WHERE starts_failure_streak) AS previous_task_id,
    MIN(previous_terminal_status) FILTER (WHERE starts_failure_streak)
        AS previous_terminal_status,
    MIN(DATE_DIFF('second', previous_started_at_wall, started_at_wall))
        FILTER (WHERE starts_failure_streak) AS seconds_since_previous_task_start,
    COUNT(DISTINCT source_batch_id) AS distinct_source_batch_count,
    STRING_AGG(DISTINCT source_batch_id, ', ' ORDER BY source_batch_id) AS source_batch_ids,
    COUNT(DISTINCT route_id) AS distinct_route_count,
    STRING_AGG(DISTINCT route_id, ', ' ORDER BY route_id) AS route_ids,
    COUNT(DISTINCT obstacle_profile) AS distinct_obstacle_count,
    STRING_AGG(DISTINCT obstacle_profile, ', ' ORDER BY obstacle_profile)
        AS obstacle_profiles,
    COUNT(DISTINCT localization_perturbation_level) AS distinct_perturbation_count,
    STRING_AGG(
        DISTINCT localization_perturbation_level, ', '
        ORDER BY localization_perturbation_level
    ) AS localization_perturbation_levels,
    STRING_AGG(task_id, ', ' ORDER BY run_order) AS task_ids,
    CASE WHEN COUNT(*) >= 2 THEN 'multi_failure_streak' ELSE 'isolated_failure' END
        AS streak_type
FROM failure_rows
GROUP BY failure_streak_id
ORDER BY start_run_order;
