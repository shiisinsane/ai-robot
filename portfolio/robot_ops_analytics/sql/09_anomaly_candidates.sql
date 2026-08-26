-- 业务问题：哪些异常满足补采门禁，应以什么优先级进入预注册控制变量实验？
-- 输入粒度：任务事实每任务一行；遥测先聚合到每任务一行。
-- 过滤条件：正式自然运行有效任务；早期窗口固定为接受后前3秒。
-- 输出粒度：每个异常候选一行。
-- 限制：early_speed_lt_0_005为看过结果后的敏感性阈值，只能作为机制支持；候选排序是
--       W6探索决策，不是模型特征选择或因果结论。未完成预注册前不得据此启动补采。

WITH cohort AS (
    SELECT
        task_id,
        terminal_status,
        route_id,
        obstacle_profile,
        localization_perturbation_level,
        accepted_at_sim,
        cycle_time_sec
    FROM fact_task_execution
    WHERE dataset_version = 'roa-data-v0.1'
      AND run_origin = 'natural'
      AND data_quality_valid = TRUE
),
totals AS (
    SELECT
        COUNT(*) AS total_task_count,
        COUNT(*) FILTER (WHERE terminal_status <> 'success') AS total_failure_count
    FROM cohort
),
early_telemetry AS (
    SELECT
        m.task_id,
        AVG(ABS(m.mean_linear_speed_mps)) FILTER (
            WHERE m.bucket_start_sim < c.accepted_at_sim + 3.0
              AND m.bucket_end_sim > c.accepted_at_sim
        ) AS early_mean_abs_linear_speed_mps
    FROM fact_task_telemetry_1s m
    JOIN cohort c USING (task_id)
    GROUP BY m.task_id
),
task_features AS (
    SELECT c.*, e.early_mean_abs_linear_speed_mps
    FROM cohort c
    LEFT JOIN early_telemetry e USING (task_id)
),
return_home_medium AS (
    SELECT
        COUNT(*) AS task_count,
        COUNT(*) FILTER (WHERE terminal_status <> 'success') AS failure_count,
        COUNT(DISTINCT localization_perturbation_level) AS perturbation_levels,
        quantile_cont(cycle_time_sec, 0.50) AS p50_cycle_time_sec,
        quantile_cont(cycle_time_sec, 0.95) AS p95_cycle_time_sec
    FROM task_features
    WHERE route_id = 'return_home' AND obstacle_profile = 'medium'
),
medium_obstacle AS (
    SELECT
        COUNT(*) AS task_count,
        COUNT(*) FILTER (WHERE terminal_status <> 'success') AS failure_count,
        COUNT(DISTINCT route_id) AS route_count,
        COUNT(DISTINCT localization_perturbation_level) AS perturbation_levels,
        quantile_cont(cycle_time_sec, 0.50) AS p50_cycle_time_sec,
        quantile_cont(cycle_time_sec, 0.95) AS p95_cycle_time_sec
    FROM task_features
    WHERE obstacle_profile = 'medium'
),
early_low_speed AS (
    SELECT
        COUNT(*) FILTER (WHERE early_mean_abs_linear_speed_mps < 0.005) AS task_count,
        COUNT(*) FILTER (
            WHERE early_mean_abs_linear_speed_mps < 0.005
              AND terminal_status <> 'success'
        ) AS failure_count,
        COUNT(*) FILTER (WHERE early_mean_abs_linear_speed_mps >= 0.005)
            AS comparator_task_count,
        COUNT(*) FILTER (
            WHERE early_mean_abs_linear_speed_mps >= 0.005
              AND terminal_status <> 'success'
        ) AS comparator_failure_count
    FROM task_features
),
candidates AS (
    SELECT
        1 AS priority,
        'A1_return_home_medium_navigation_failure' AS candidate_id,
        'return_home × medium导航失败集中' AS candidate_name,
        r.task_count,
        r.failure_count,
        r.failure_count::DOUBLE / NULLIF(r.task_count, 0) AS failure_rate,
        r.failure_count::DOUBLE / NULLIF(t.total_failure_count, 0)
            AS failure_contribution,
        r.p50_cycle_time_sec,
        r.p95_cycle_time_sec,
        '9项跨3档定位扰动重复失败，均为导航错误201且未进入sensing' AS evidence_summary,
        '固定return_home、定位扰动和baseline参数，仅改变low/medium障碍' AS falsifiable_test,
        TRUE AS reproducible_sql,
        r.task_count > 1 AS not_single_task,
        r.perturbation_levels = 3 AS repeated_across_planned_groups,
        TRUE AS data_quality_cleared,
        TRUE AS single_factor_experiment_possible,
        TRUE AS metric_pre_registered,
        'eligible_for_preregistration' AS gate_decision
    FROM return_home_medium r CROSS JOIN totals t

    UNION ALL

    SELECT
        2,
        'A2_medium_obstacle_failure_concentration',
        'medium障碍失败集中',
        m.task_count,
        m.failure_count,
        m.failure_count::DOUBLE / NULLIF(m.task_count, 0),
        m.failure_count::DOUBLE / NULLIF(t.total_failure_count, 0),
        m.p50_cycle_time_sec,
        m.p95_cycle_time_sec,
        '覆盖3条路线和3档定位扰动，但13项失败中的9项来自return_home',
        '作为A1的上位证据；实验中保持路线与定位扰动固定后改变障碍档位',
        TRUE,
        m.task_count > 1,
        m.route_count = 3 AND m.perturbation_levels = 3,
        TRUE,
        TRUE,
        TRUE,
        'supporting_parent_candidate'
    FROM medium_obstacle m CROSS JOIN totals t

    UNION ALL

    SELECT
        3,
        'A3_early_low_speed_association',
        '接受后前3秒低速与失败相关',
        e.task_count,
        e.failure_count,
        e.failure_count::DOUBLE / NULLIF(e.task_count, 0),
        e.failure_count::DOUBLE / NULLIF(t.total_failure_count, 0),
        NULL::DOUBLE,
        NULL::DOUBLE,
        '事后阈值<0.005m/s命中13/15项失败，但也命中23/66项成功',
        '在A1控制实验中作为连续观测指标，不以该阈值决定入组或停止',
        TRUE,
        e.task_count > 1,
        TRUE,
        TRUE,
        FALSE,
        FALSE,
        'supporting_mechanism_only'
    FROM early_low_speed e CROSS JOIN totals t
)
SELECT
    priority,
    candidate_id,
    candidate_name,
    task_count,
    failure_count,
    failure_rate,
    failure_contribution,
    p50_cycle_time_sec,
    p95_cycle_time_sec,
    evidence_summary,
    falsifiable_test,
    reproducible_sql,
    not_single_task,
    repeated_across_planned_groups,
    data_quality_cleared,
    single_factor_experiment_possible,
    metric_pre_registered,
    gate_decision
FROM candidates
ORDER BY priority;
