-- 业务问题：15项失败由哪些错误码和场景组合主导，累计贡献如何？
-- 输入粒度：fact_task_execution 每任务一行。
-- 过滤条件：正式自然运行有效队列；失败定义为terminal_status<>'success'。
-- 输出粒度：error_code每错误码一行，scenario_combination每个出现失败的组合一行；
--           两种pareto_type分别排名和计算累计贡献，不得跨类型相加。
-- 限制：错误码只能说明记录到的终态类型；场景组合每格仅3项，结果用于确定排查优先级，
--       不构成障碍、路线或定位扰动导致失败的因果证据。

WITH cohort AS (
    SELECT
        task_id,
        route_id,
        obstacle_profile,
        localization_perturbation_level,
        terminal_status,
        error_code,
        result_message
    FROM fact_task_execution
    WHERE dataset_version = 'roa-data-v0.1'
      AND run_origin = 'natural'
      AND data_quality_valid = TRUE
),
failures AS (
    SELECT * FROM cohort WHERE terminal_status <> 'success'
),
totals AS (
    SELECT
        (SELECT COUNT(*) FROM cohort) AS cohort_task_count,
        (SELECT COUNT(*) FROM failures) AS total_failure_count
),
error_items AS (
    SELECT
        'error_code' AS pareto_type,
        'error_code=' || CAST(error_code AS VARCHAR) AS item_key,
        NULL::VARCHAR AS route_id,
        NULL::VARCHAR AS obstacle_profile,
        NULL::VARCHAR AS localization_perturbation_level,
        error_code,
        MIN(result_message) AS representative_message,
        COUNT(DISTINCT result_message) AS distinct_message_count,
        t.cohort_task_count AS exposure_count,
        COUNT(*) AS failure_count
    FROM failures
    CROSS JOIN totals t
    GROUP BY error_code, t.cohort_task_count
),
scenario_exposure AS (
    SELECT route_id, obstacle_profile, localization_perturbation_level,
           COUNT(*) AS exposure_count
    FROM cohort
    GROUP BY route_id, obstacle_profile, localization_perturbation_level
),
scenario_items AS (
    SELECT
        'scenario_combination' AS pareto_type,
        f.route_id || ' × ' || f.obstacle_profile || ' × '
            || f.localization_perturbation_level AS item_key,
        f.route_id,
        f.obstacle_profile,
        f.localization_perturbation_level,
        NULL::BIGINT AS error_code,
        NULL::VARCHAR AS representative_message,
        NULL::BIGINT AS distinct_message_count,
        e.exposure_count,
        COUNT(*) AS failure_count
    FROM failures f
    JOIN scenario_exposure e USING (
        route_id, obstacle_profile, localization_perturbation_level)
    GROUP BY f.route_id, f.obstacle_profile, f.localization_perturbation_level,
             e.exposure_count
),
items AS (
    SELECT * FROM error_items
    UNION ALL
    SELECT * FROM scenario_items
),
ranked AS (
    SELECT
        i.*,
        i.failure_count::DOUBLE / NULLIF(i.exposure_count, 0) AS failure_rate,
        i.failure_count::DOUBLE / NULLIF(t.total_failure_count, 0) AS failure_contribution,
        ROW_NUMBER() OVER (
            PARTITION BY i.pareto_type
            ORDER BY i.failure_count DESC, i.item_key) AS pareto_rank,
        SUM(i.failure_count) OVER (
            PARTITION BY i.pareto_type
            ORDER BY i.failure_count DESC, i.item_key
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )::DOUBLE / NULLIF(t.total_failure_count, 0) AS cumulative_failure_contribution
    FROM items i
    CROSS JOIN totals t
)
SELECT
    pareto_type,
    pareto_rank,
    item_key,
    route_id,
    obstacle_profile,
    localization_perturbation_level,
    error_code,
    representative_message,
    distinct_message_count,
    exposure_count,
    failure_count,
    failure_rate,
    failure_contribution,
    cumulative_failure_contribution,
    CASE
        WHEN pareto_type = 'scenario_combination' AND exposure_count < 5 THEN 'small_sample'
        ELSE 'adequate_for_exploration'
    END AS sample_size_flag
FROM ranked
ORDER BY CASE pareto_type WHEN 'error_code' THEN 0 ELSE 1 END, pareto_rank;
